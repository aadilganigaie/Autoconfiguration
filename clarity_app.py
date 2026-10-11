"""CLARITY - Industrial Device Auto-Configuration Web Application.

A Streamlit front end for the CLARITY pipeline: upload device documentation,
select a target protocol (Modbus TCP, OPC UA, PROFIBUS, generic fieldbus),
click Auto-configure, and get a verified deployment status.

Run:
    streamlit run clarity_app.py --server.port 8501 --server.address 0.0.0.0
"""
import hashlib
import json
import socket
import sys
import time
from datetime import datetime
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

UPLOAD_DIR = ROOT / "uploads"
RESULTS_DIR = ROOT / "clarity" / "evaluation" / "results"

st.set_page_config(
    page_title="CLARITY Auto-Configuration",
    page_icon="⚙️",
    layout="wide",
    initial_sidebar_state="expanded",
)

PROTOCOLS = {
    "Modbus TCP": "modbus",
    "OPC UA": "opcua",
    "PROFIBUS": "profibus",
    "Generic fieldbus": "fieldbus",
}

DEFAULT_TAU = 0.72
DEFAULT_OLLAMA = "http://localhost:11434"
DEFAULT_MODEL = "llama3.1:8b"


# ============================================================================
# Cached heavy resources (loaded once per process, shared across reruns)
# ============================================================================

@st.cache_resource(show_spinner="Starting embedded vector store...")
def get_kb() -> dict:
    """Knowledge base singleton: embedded in-memory Qdrant + BM25 + chunk cache.

    Uses the same embedded-Qdrant pattern as the evaluation harness so the app
    needs no external Qdrant server.
    """
    import qdrant_client

    import clarity.retrieval.vector_store as vs_mod
    from clarity.config import ClarityConfig
    from clarity.retrieval.sparse_retriever import SparseRetriever

    embedded = qdrant_client.QdrantClient(":memory:")
    original = vs_mod.QdrantClient
    vs_mod.QdrantClient = lambda host=None, port=None: embedded
    try:
        store = vs_mod.VectorStore(ClarityConfig())
    finally:
        vs_mod.QdrantClient = original

    return {
        "store": store,
        "sparse": SparseRetriever(),
        "chunks": [],
        "docs": [],  # [{name, path, sha256, pages, chunks, seconds, ingested_at}]
    }


@st.cache_resource(show_spinner="Loading embedding model (BGE-M3)...")
def get_embedder(model_name: str):
    from clarity.retrieval.embedder import Embedder
    return Embedder(model_name)


@st.cache_resource(show_spinner="Loading cross-encoder reranker...")
def get_reranker(model_name: str):
    from clarity.retrieval.reranker import Reranker
    return Reranker(model_name)


@st.cache_resource(show_spinner="Loading ontologies...")
def get_ontology_stack():
    from clarity.config import DEFAULT_CONFIG
    from clarity.generation.iri_resolver import IRIResolver
    from clarity.ingestion.ontology_loader import OntologyLoader
    from clarity.retrieval.graph_retriever import GraphRetriever

    ontology = OntologyLoader(DEFAULT_CONFIG.ontologies_dir)
    return {
        "ontology": ontology,
        "graph": GraphRetriever(ontology),
        "iri": IRIResolver(ontology),
    }


@st.cache_resource(show_spinner="Loading SHACL shapes...")
def get_shacl_validator():
    from clarity.config import DEFAULT_CONFIG
    from clarity.validation.shacl_validator import SHACLValidator
    return SHACLValidator(DEFAULT_CONFIG.shacl_shapes_dir)


# ============================================================================
# Small helpers
# ============================================================================

def _ping(url: str, timeout: float = 1.5) -> tuple[bool, str]:
    try:
        import httpx
        r = httpx.get(url, timeout=timeout)
        return r.status_code < 400, f"HTTP {r.status_code}"
    except Exception as e:
        return False, str(e)[:60]


def _tcp(host: str, port: int, timeout: float = 1.5) -> tuple[bool, str]:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, "port open"
    except Exception as e:
        return False, str(e)[:60]


def _ollama_models(host: str) -> list[str]:
    try:
        import httpx
        r = httpx.get(f"{host.rstrip('/')}/api/tags", timeout=2)
        return [m["name"] for m in r.json().get("models", [])]
    except Exception:
        return []


def _opcua_hostport(endpoint: str) -> tuple[str, int] | None:
    try:
        rest = endpoint.split("://", 1)[1]
        hostport = rest.split("/", 1)[0]
        host, _, port = hostport.partition(":")
        return host, int(port or 4840)
    except Exception:
        return None


def _init_state():
    st.session_state.setdefault("history", [])
    st.session_state.setdefault("last_run", None)


def _sup(s, **kwargs):
    """Update a status container; tolerates bare mode where st.status yields None."""
    if s is not None:
        s.update(**kwargs)


# ============================================================================
# Knowledge base operations
# ============================================================================

def _pages_from_text(text: str, source_path: str):
    """Wrap a plain-text or markdown document as one PageContent per ~3000 chars."""
    from clarity.ingestion.pdf_parser import PageContent
    step = 3000
    blocks = [text[i:i + step] for i in range(0, max(len(text), 1), step)]
    return [
        PageContent(page_num=i + 1, text=block, tables=[], source_path=source_path)
        for i, block in enumerate(blocks)
    ]


def ingest_uploaded_files(uploaded_files) -> list[dict]:
    """Save uploads, parse, chunk, embed, and index them. Returns per-file reports."""
    from clarity.ingestion.chunker import chunk_document
    from clarity.ingestion.pdf_parser import parse_pdf

    kb = get_kb()
    embedder = get_embedder("BAAI/bge-m3")
    UPLOAD_DIR.mkdir(exist_ok=True)

    reports = []
    for uf in uploaded_files:
        data = uf.read()
        sha = hashlib.sha256(data).hexdigest()

        if any(d["sha256"] == sha for d in kb["docs"]):
            reports.append({"name": uf.name, "status": "skipped (already ingested)"})
            continue

        dest = UPLOAD_DIR / uf.name
        if dest.exists() and hashlib.sha256(dest.read_bytes()).hexdigest() != sha:
            dest = UPLOAD_DIR / f"{dest.stem}_{sha[:8]}{dest.suffix}"
        dest.write_bytes(data)

        t0 = time.monotonic()
        try:
            if dest.suffix.lower() == ".pdf":
                pages = parse_pdf(dest)
            else:
                pages = _pages_from_text(data.decode("utf-8", errors="replace"), str(dest))

            chunks = chunk_document(pages, str(dest))
            if not chunks:
                reports.append({"name": uf.name, "status": "no extractable text"})
                continue

            embeddings = embedder.embed_texts([c.text for c in chunks])
            kb["store"].upsert_chunks(chunks, embeddings)
            kb["chunks"].extend(chunks)
            kb["sparse"].build_index(kb["chunks"])

            elapsed = time.monotonic() - t0
            kb["docs"].append({
                "name": uf.name,
                "path": str(dest),
                "sha256": sha,
                "pages": len(pages),
                "chunks": len(chunks),
                "seconds": round(elapsed, 1),
                "ingested_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            })
            reports.append({
                "name": uf.name,
                "status": f"ingested: {len(pages)} pages, {len(chunks)} chunks in {elapsed:.1f}s",
            })
        except Exception as e:
            reports.append({"name": uf.name, "status": f"error: {e}"})

    return reports


def clear_knowledge_base():
    get_kb.clear()


# ============================================================================
# Pipeline stages (mirrors ClarityPipeline.configure_device, instrumented)
# ============================================================================

def retrieve_evidence(query: str, dense_top_k: int, sparse_top_k: int, rerank_top_n: int):
    """Dense + sparse + ontology-graph retrieval, RRF fusion, cross-encoder rerank."""
    from clarity.retrieval.hybrid_fusion import hybrid_fuse

    kb = get_kb()
    embedder = get_embedder("BAAI/bge-m3")
    reranker = get_reranker("cross-encoder/ms-marco-MiniLM-L-6-v2")
    stack = get_ontology_stack()

    timings = {}
    t0 = time.monotonic()
    q_emb = embedder.embed_query(query)
    timings["embed_query_ms"] = (time.monotonic() - t0) * 1000

    t0 = time.monotonic()
    dense = kb["store"].search(q_emb, top_k=dense_top_k)
    sparse = kb["sparse"].search(query, top_k=sparse_top_k)
    graph_terms = stack["graph"].find_relevant_terms(query)
    fused = hybrid_fuse(dense, sparse, graph_terms)
    timings["search_fuse_ms"] = (time.monotonic() - t0) * 1000

    t0 = time.monotonic()
    ranked = reranker.rerank(query, fused, top_n=rerank_top_n)
    timings["rerank_ms"] = (time.monotonic() - t0) * 1000

    return ranked, graph_terms, timings


def make_deployer(protocol: str, conn: dict):
    from clarity.protocols.fieldbus_deployer import FieldbusDeployer
    from clarity.protocols.modbus_deployer import ModbusDeployer
    from clarity.protocols.opcua_deployer import OpcUaDeployer
    from clarity.protocols.profibus_deployer import ProfibusDeployer

    if protocol == "modbus":
        return ModbusDeployer(conn["modbus_host"], conn["modbus_port"])
    if protocol == "opcua":
        return OpcUaDeployer(conn["opcua_endpoint"])
    if protocol == "profibus":
        return ProfibusDeployer()
    return FieldbusDeployer()


def run_autoconfiguration(params: dict) -> dict:
    """Execute the full pipeline with a live status block per stage."""
    from clarity.config import ClarityConfig
    from clarity.generation.jsonld_generator import JsonLdGenerator
    from clarity.generation.llm_client import LLMClient

    proto = params["protocol"]
    run: dict = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "device": params["device_name"],
        "protocol": proto,
        "status": "failed",
        "detail": "",
        "s_max": None,
        "abstained": False,
        "shacl_valid": False,
        "deployed": False,
        "jsonld": None,
        "evidence": [],
        "deployed_values": {},
        "stage_latency_ms": {},
    }
    t_start = time.monotonic()

    # Stage 1: retrieval -----------------------------------------------------
    with st.status("Stage 1 of 6: Retrieving evidence from knowledge base...", expanded=True) as s:
        query = (
            f"{params['device_name']} {proto} configuration parameters "
            f"{params['description']} {params['extra_context']}"
        ).strip()
        st.write(f"Query: `{query}`")
        t0 = time.monotonic()
        ranked, graph_terms, timings = retrieve_evidence(
            query, params["dense_top_k"], params["sparse_top_k"], params["rerank_top_n"]
        )
        run["stage_latency_ms"]["retrieval"] = (time.monotonic() - t0) * 1000
        run["stage_latency_ms"].update(timings)

        if not ranked:
            run.update(status="abstained", abstained=True,
                       detail="No relevant documentation found in the knowledge base.")
            _sup(s, label="Stage 1: No evidence found", state="error", expanded=True)
            st.error("The knowledge base returned no candidate chunks for this device. "
                     "Upload the device manual first.")
            return _finish_run(run, t_start)

        run["evidence"] = [
            {
                "rank": i + 1,
                "score": round(r.rerank_score, 4),
                "source": Path(r.source_path).name,
                "page": r.page_num,
                "type": r.chunk_type,
                "text": r.text,
            }
            for i, r in enumerate(ranked)
        ]
        run["s_max"] = max(r.rerank_score for r in ranked)
        import pandas as pd
        st.dataframe(
            pd.DataFrame([{k: v for k, v in e.items() if k != "text"} for e in run["evidence"]]),
            width="stretch", hide_index=True,
        )
        st.caption(f"{len(graph_terms)} ontology terms matched for graph boosting.")
        _sup(s, label=f"Stage 1: Retrieved {len(ranked)} evidence chunks "
                       f"({run['stage_latency_ms']['retrieval'] / 1000:.1f}s)", state="complete")

    # Stage 2: confidence gate -----------------------------------------------
    with st.status("Stage 2 of 6: Abstention confidence gate...", expanded=True) as s:
        tau = params["threshold"]
        c1, c2 = st.columns(2)
        c1.metric("Max rerank score s_max", f"{run['s_max']:.4f}")
        c2.metric("Threshold τ", f"{tau:.4f}")
        if run["s_max"] < tau:
            run.update(status="abstained", abstained=True,
                       detail=f"Retrieval confidence {run['s_max']:.3f} is below τ = {tau:.2f}.")
            _sup(s, label="Stage 2: Gate ABSTAINED (confidence too low)", state="error", expanded=True)
            st.warning(
                "The system abstained rather than guess. Either the uploaded documents do not "
                "cover this request, or τ needs recalibration for this corpus. Run a retrieval "
                "dry run to inspect scores; the recommended recalibration is the midpoint of the "
                "measured gap between answerable and unanswerable scores."
            )
            return _finish_run(run, t_start)
        st.success(f"Gate passed: s_max {run['s_max']:.3f} ≥ τ {tau:.2f}. Proceeding to generation.")
        _sup(s, label="Stage 2: Confidence gate passed", state="complete")

    # Stage 3: LLM generation ------------------------------------------------
    with st.status("Stage 3 of 6: Generating JSON-LD configuration with the LLM...", expanded=True) as s:
        cfg = ClarityConfig(
            ollama_host=params["ollama_host"],
            ollama_model=params["ollama_model"],
            abstention_threshold=tau,
            rerank_top_n=params["rerank_top_n"],
        )
        llm = LLMClient(cfg)
        if not llm.health_check():
            run["detail"] = f"Ollama is unreachable at {params['ollama_host']}."
            _sup(s, label="Stage 3: Ollama unreachable", state="error", expanded=True)
            st.error(run["detail"] + " Start the Ollama server and retry.")
            return _finish_run(run, t_start)

        generator = JsonLdGenerator(llm, get_ontology_stack()["iri"], cfg)
        st.write(f"Model: `{params['ollama_model']}`  |  temperature 0.1  |  schema-constrained decoding")
        t0 = time.monotonic()
        jsonld = generator.generate_config(
            params["device_name"], params["description"], ranked, proto
        )
        run["stage_latency_ms"]["llm_generate"] = (time.monotonic() - t0) * 1000

        if jsonld.get("abstained"):
            reason = jsonld.get("reason", "The generator abstained.")
            partial = jsonld.get("partial_config") or {}
            if reason == "All checks passed." and "raw_response" in partial:
                reason = ("The LLM output could not be parsed as valid JSON-LD even after "
                          "repair, so the system abstained rather than deploy an unreliable "
                          "configuration. Retry, or try a different model.")
            run.update(status="abstained", abstained=True, jsonld=jsonld, detail=reason)
            _sup(s, label="Stage 3: Generator ABSTAINED", state="error", expanded=True)
            st.warning(run["detail"])
            if partial:
                with st.expander("Partial / raw LLM output"):
                    st.json(partial, expanded=False)
            return _finish_run(run, t_start)

        run["jsonld"] = jsonld
        st.json(jsonld, expanded=False)
        _sup(s, label=f"Stage 3: Configuration generated "
                       f"({run['stage_latency_ms']['llm_generate'] / 1000:.1f}s)", state="complete")

    # Stage 4: IRI resolution ------------------------------------------------
    with st.status("Stage 4 of 6: Resolving ontology IRIs...", expanded=True) as s:
        iri_result = get_ontology_stack()["iri"].validate_jsonld_iris(run["jsonld"])
        c1, c2, c3 = st.columns(3)
        c1.metric("Resolved IRIs", len(iri_result.resolved_iris))
        c2.metric("Unresolved terms", len(iri_result.unresolved_terms))
        c3.metric("Resolution confidence", f"{iri_result.resolution_confidence:.2f}")
        if iri_result.unresolved_terms:
            st.caption("Unresolved: " + ", ".join(iri_result.unresolved_terms[:10]))
        _sup(s, label="Stage 4: IRI resolution complete", state="complete")

    # Stage 5: SHACL validation ----------------------------------------------
    with st.status("Stage 5 of 6: Validating against SHACL safety shapes...", expanded=True) as s:
        t0 = time.monotonic()
        shacl_result = get_shacl_validator().validate(run["jsonld"], proto)
        run["stage_latency_ms"]["shacl"] = (time.monotonic() - t0) * 1000
        run["shacl_valid"] = shacl_result.conforms
        if not shacl_result.conforms:
            run["detail"] = f"SHACL validation failed with {len(shacl_result.violations)} violation(s)."
            for v in shacl_result.violations:
                st.code(v)
            _sup(s, label="Stage 5: SHACL validation FAILED (deployment blocked)",
                     state="error", expanded=True)
            st.error("The generated configuration violates the protocol safety shapes. "
                     "Nothing was written to the device.")
            return _finish_run(run, t_start)
        st.success("Configuration conforms to the protocol SHACL shapes.")
        _sup(s, label="Stage 5: SHACL validation passed", state="complete")

    # Stage 6: deploy + read-back verification ---------------------------------
    with st.status("Stage 6 of 6: Deploying to device and verifying by read-back...",
                   expanded=True) as s:
        deployer = make_deployer(proto, params["connection"])
        t0 = time.monotonic()
        try:
            deploy_result = deployer.deploy_config(run["jsonld"])
        except Exception as e:
            run["detail"] = f"Deployment error: {e}"
            _sup(s, label="Stage 6: Deployment error", state="error", expanded=True)
            st.error(run["detail"])
            return _finish_run(run, t_start)
        run["stage_latency_ms"]["deploy"] = (time.monotonic() - t0) * 1000

        run["deployed"] = deploy_result.success
        run["deployed_values"] = deploy_result.deployed_values

        if deploy_result.safety_violations:
            for v in deploy_result.safety_violations:
                st.error(v)
        if deploy_result.verification_errors:
            for e in deploy_result.verification_errors:
                st.warning(e)

        if deploy_result.success:
            if deploy_result.deployed_values:
                st.write("Deployed values (verified by independent read-back):")
                st.json(deploy_result.deployed_values, expanded=True)
            _sup(s, label=f"Stage 6: Deployed and verified "
                           f"({run['stage_latency_ms']['deploy'] / 1000:.2f}s)", state="complete")
            run.update(status="success", detail="Configuration deployed and verified on the device.")
        else:
            run["detail"] = "Deployment failed or read-back verification did not match."
            _sup(s, label="Stage 6: Deployment FAILED", state="error", expanded=True)

    return _finish_run(run, t_start)


def _finish_run(run: dict, t_start: float) -> dict:
    run["total_latency_ms"] = (time.monotonic() - t_start) * 1000
    st.session_state["history"].append(run)
    st.session_state["last_run"] = run
    return run


def render_final_banner(run: dict):
    st.divider()
    if run["status"] == "success":
        st.success(
            f"✅ **Device configured successfully.** {run['device']} was configured over "
            f"{run['protocol'].upper()} in {run['total_latency_ms'] / 1000:.1f}s. "
            "The configuration passed SHACL safety validation and was verified on the "
            "device by independent read-back."
        )
    elif run["status"] == "abstained":
        st.warning(
            f"⚠️ **Configuration abstained (no unsafe write was attempted).** {run['detail']} "
            "The device was not touched. Upload better documentation or adjust the threshold."
        )
    else:
        st.error(f"❌ **Configuration failed.** {run['detail']} ")

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Outcome", run["status"].upper())
    c2.metric("Retrieval s_max", f"{run['s_max']:.3f}" if run["s_max"] is not None else "n/a")
    c3.metric("SHACL valid", "yes" if run["shacl_valid"] else "no")
    c4.metric("Deployed", "yes" if run["deployed"] else "no")
    c5.metric("Total latency", f"{run['total_latency_ms'] / 1000:.1f} s")

    if run["stage_latency_ms"]:
        with st.expander("Per-stage latency"):
            import pandas as pd
            rows = [{"stage": k, "latency_ms": round(v, 1)}
                    for k, v in run["stage_latency_ms"].items()]
            st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    if run["evidence"]:
        with st.expander("Evidence chunks used (provenance)"):
            for e in run["evidence"]:
                st.markdown(
                    f"**Rank {e['rank']}** | score {e['score']} | "
                    f"`{e['source']}` page {e['page']} | {e['type']}"
                )
                st.text(e["text"][:1200])

    if run["jsonld"]:
        with st.expander("Generated JSON-LD configuration", expanded=(run["status"] == "success")):
            st.json(run["jsonld"])
        st.download_button(
            "⬇ Download JSON-LD configuration",
            data=json.dumps(run["jsonld"], indent=2),
            file_name=f"{run['device'].replace(' ', '_')}_{run['protocol']}_config.jsonld",
            mime="application/ld+json",
        )


# ============================================================================
# Page: Auto-Configure (main workflow)
# ============================================================================

def page_autoconfigure():
    st.title("⚙️ Device Auto-Configuration")
    st.caption(
        "Upload the device documentation, pick the target protocol, and let CLARITY "
        "retrieve the relevant parameters, generate a validated configuration, and "
        "deploy it to the device with read-back verification."
    )

    kb = get_kb()

    # Step 1 -------------------------------------------------------------
    st.header("Step 1: Device documentation")
    uploads = st.file_uploader(
        "Upload device manuals or datasheets (PDF, TXT, MD). You can add several files.",
        type=["pdf", "txt", "md"],
        accept_multiple_files=True,
    )
    col_a, col_b = st.columns([1, 1])
    if col_a.button("📥 Ingest into knowledge base", disabled=not uploads):
        with st.spinner("Parsing, chunking, embedding, and indexing..."):
            reports = ingest_uploaded_files(uploads)
        for r in reports:
            if r["status"].startswith("ingested"):
                st.success(f"{r['name']}: {r['status']}")
            elif r["status"].startswith("skipped"):
                st.info(f"{r['name']}: {r['status']}")
            else:
                st.error(f"{r['name']}: {r['status']}")

    if col_b.button("🗑 Clear knowledge base", disabled=not kb["docs"]):
        clear_knowledge_base()
        st.rerun()

    if kb["docs"]:
        import pandas as pd
        st.dataframe(
            pd.DataFrame(kb["docs"])[["name", "pages", "chunks", "seconds", "ingested_at"]],
            width="stretch", hide_index=True,
        )
        st.caption(f"Knowledge base: {len(kb['docs'])} document(s), {len(kb['chunks'])} chunks total.")
    else:
        st.info("The knowledge base is empty. Upload at least one document before configuring.")

    # Step 2 -------------------------------------------------------------
    st.header("Step 2: Device and protocol")
    c1, c2 = st.columns(2)
    device_name = c1.text_input("Device name", value="", placeholder="e.g. UR5e collaborative robot")
    protocol_label = c2.selectbox("Target protocol", list(PROTOCOLS.keys()))
    protocol = PROTOCOLS[protocol_label]

    description = st.text_area(
        "Commissioning request / device description",
        placeholder=(
            "Describe what should be configured, like a work order. Example: write the "
            "commissioning values 0, 0, 0, 1 to general purpose registers 128 to 131 "
            "using FC 0x06 Write Single Register."
        ),
        height=90,
    )
    extra_context = st.text_input(
        "Extra context (optional)", placeholder="e.g. slave address 3, baud rate 19200"
    )

    conn = {"modbus_host": "localhost", "modbus_port": 5020,
            "opcua_endpoint": "opc.tcp://localhost:4840"}
    if protocol == "modbus":
        c3, c4, c5 = st.columns([2, 1, 1])
        conn["modbus_host"] = c3.text_input("Device / bridge host", value="localhost")
        conn["modbus_port"] = int(c4.number_input("Port", value=5020, step=1, min_value=1, max_value=65535))
        st.caption("Port 5020 is the pymodbus simulator; port 5021 is the UR5e MuJoCo bridge.")
        if c5.button("🔌 Test connection"):
            ok, msg = _tcp(conn["modbus_host"], conn["modbus_port"])
            (st.success if ok else st.error)(f"Modbus TCP {conn['modbus_host']}:{conn['modbus_port']}: {msg}")
    elif protocol == "opcua":
        c3, c4 = st.columns([3, 1])
        conn["opcua_endpoint"] = c3.text_input("OPC UA endpoint", value="opc.tcp://localhost:4840")
        if c4.button("🔌 Test connection"):
            hp = _opcua_hostport(conn["opcua_endpoint"])
            if hp is None:
                st.error("Endpoint could not be parsed. Expected opc.tcp://host:port")
            else:
                ok, msg = _tcp(*hp)
                (st.success if ok else st.error)(f"OPC UA {hp[0]}:{hp[1]}: {msg}")
    else:
        st.caption("This protocol uses the built-in simulated deployer; no connection settings needed.")

    # Advanced settings ----------------------------------------------------
    with st.expander("Advanced settings"):
        c6, c7 = st.columns(2)
        ollama_host = c6.text_input("Ollama host", value=DEFAULT_OLLAMA)
        models = _ollama_models(ollama_host)
        if models:
            default_idx = models.index(DEFAULT_MODEL) if DEFAULT_MODEL in models else 0
            ollama_model = c7.selectbox("LLM model", models, index=default_idx)
        else:
            ollama_model = c7.text_input("LLM model", value=DEFAULT_MODEL)
            st.caption("Ollama is not reachable right now, so the model list could not be fetched.")

        c8, c9, c10, c11 = st.columns(4)
        threshold = c8.number_input(
            "Abstention threshold τ", min_value=0.0, max_value=1.0, value=DEFAULT_TAU, step=0.01,
            help=(
                "Benchmark-calibrated default. The threshold is corpus dependent: on a new "
                "document set, run a retrieval dry run first and set τ inside the gap between "
                "answerable and unanswerable scores (midpoint recommended)."
            ),
        )
        dense_top_k = int(c9.number_input("Dense top-k", 5, 50, 20))
        sparse_top_k = int(c10.number_input("Sparse top-k", 5, 50, 20))
        rerank_top_n = int(c11.number_input("Rerank top-N", 1, 10, 5))

    # Step 3 -------------------------------------------------------------
    st.header("Step 3: Run")
    ready = bool(kb["docs"]) and bool(device_name.strip()) and bool(description.strip())
    if not ready:
        st.caption("Provide at least one ingested document, a device name, and a commissioning request.")

    params = {
        "device_name": device_name.strip(),
        "protocol": protocol,
        "description": description.strip(),
        "extra_context": extra_context.strip(),
        "threshold": threshold,
        "dense_top_k": dense_top_k,
        "sparse_top_k": sparse_top_k,
        "rerank_top_n": rerank_top_n,
        "ollama_host": ollama_host,
        "ollama_model": ollama_model,
        "connection": conn,
    }

    col_run, col_dry = st.columns([1, 1])
    if col_run.button("🚀 Auto-configure device", type="primary", disabled=not ready):
        run = run_autoconfiguration(params)
        render_final_banner(run)

    if col_dry.button("🔍 Retrieval dry run (no LLM, no deployment)", disabled=not ready):
        query = f"{params['device_name']} {protocol} configuration parameters {params['description']} {params['extra_context']}".strip()
        with st.spinner("Running retrieval only..."):
            ranked, graph_terms, timings = retrieve_evidence(
                query, dense_top_k, sparse_top_k, rerank_top_n
            )
        if not ranked:
            st.error("No candidates retrieved. The knowledge base may not cover this device.")
        else:
            s_max = max(r.rerank_score for r in ranked)
            c1, c2, c3 = st.columns(3)
            c1.metric("s_max", f"{s_max:.4f}")
            c2.metric("Current τ", f"{threshold:.2f}")
            c3.metric("Gate decision", "PROCEED" if s_max >= threshold else "ABSTAIN")
            if s_max < threshold:
                st.warning(
                    f"With τ = {threshold:.2f} this request would abstain. If you believe the "
                    f"documents do answer it, lower τ below {s_max:.3f} or recalibrate from a "
                    "small set of answerable and unanswerable probe queries."
                )
            import pandas as pd
            st.dataframe(pd.DataFrame([
                {"rank": i + 1, "score": round(r.rerank_score, 4),
                 "source": Path(r.source_path).name, "page": r.page_num,
                 "preview": r.text[:160]}
                for i, r in enumerate(ranked)
            ]), width="stretch", hide_index=True)


# ============================================================================
# Page: System Health
# ============================================================================

def page_health():
    st.title("🖥 System Health")
    if st.button("🔄 Refresh"):
        st.rerun()

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Services")
        ok_o, msg_o = _ping(f"{DEFAULT_OLLAMA}/api/tags")
        st.metric("Ollama (LLM server)", "🟢 up" if ok_o else "🔴 down", msg_o)
        ok_mb, msg_mb = _tcp("localhost", 5020)
        st.metric("Modbus simulator (:5020)", "🟢 up" if ok_mb else "🔴 down", msg_mb)
        ok_ur, msg_ur = _tcp("localhost", 5021)
        st.metric("UR5e MuJoCo bridge (:5021)", "🟢 up" if ok_ur else "🔴 down", msg_ur)
        ok_ua, msg_ua = _tcp("localhost", 4840)
        st.metric("OPC UA server (:4840)", "🟢 up" if ok_ua else "🔴 down", msg_ua)
        st.caption("The vector store runs embedded in this app, so no Qdrant server is required.")

        st.subheader("Ollama models")
        models = _ollama_models(DEFAULT_OLLAMA)
        if models:
            for m in models:
                st.write(f"• `{m}`")
        else:
            st.warning("No models listed (Ollama down or none pulled).")

    with col2:
        st.subheader("Python dependencies")
        deps = [
            ("streamlit", "Streamlit"),
            ("sentence_transformers", "SentenceTransformers"),
            ("qdrant_client", "Qdrant client (embedded mode)"),
            ("rank_bm25", "BM25 (rank_bm25)"),
            ("pymodbus", "pymodbus"),
            ("asyncua", "asyncua (OPC UA)"),
            ("rdflib", "rdflib"),
            ("pyshacl", "pySHACL"),
            ("ollama", "Ollama SDK"),
            ("pymupdf4llm", "pymupdf4llm (PDF parsing)"),
        ]
        for mod, label in deps:
            try:
                __import__(mod)
                st.success(f"✅ {label}")
            except ImportError:
                st.error(f"❌ {label} not installed")

    st.divider()
    kb = get_kb()
    st.subheader("Knowledge base")
    c1, c2 = st.columns(2)
    c1.metric("Documents", len(kb["docs"]))
    c2.metric("Chunks indexed", len(kb["chunks"]))


# ============================================================================
# Page: Run History
# ============================================================================

def page_history():
    st.title("🕘 Run History")
    history = st.session_state["history"]
    if not history:
        st.info("No runs in this session yet.")
        return

    import pandas as pd
    rows = [
        {
            "time": r["timestamp"], "device": r["device"], "protocol": r["protocol"],
            "outcome": r["status"], "s_max": round(r["s_max"], 3) if r["s_max"] is not None else None,
            "SHACL": r["shacl_valid"], "deployed": r["deployed"],
            "latency_s": round(r["total_latency_ms"] / 1000, 1),
        }
        for r in history
    ]
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    idx = st.selectbox(
        "Inspect run", range(len(history)),
        format_func=lambda i: f"{history[i]['timestamp']} | {history[i]['device']} | {history[i]['status']}",
    )
    run = history[idx]
    render_final_banner(run)

    st.download_button(
        "⬇ Download full run record (JSON)",
        data=json.dumps(run, indent=2, default=str),
        file_name=f"clarity_run_{idx}.json",
        mime="application/json",
    )


# ============================================================================
# Page: Evaluation Results (real measured numbers from the results JSONs)
# ============================================================================

def page_evaluation():
    st.title("📊 Evaluation Results")
    st.caption(
        "Measured results loaded from clarity/evaluation/results. Every number shown "
        "here comes from an actual recorded run; nothing is hardcoded in the app."
    )

    json_files = sorted(RESULTS_DIR.glob("*.json")) if RESULTS_DIR.exists() else []
    csv_files = sorted(ROOT.glob("clarity_benchmark*.csv"))

    if not json_files and not csv_files:
        st.info("No result files found yet. Run the evaluation harness first.")
        return

    for jf in json_files:
        with st.expander(f"📄 {jf.name}", expanded=False):
            try:
                data = json.loads(jf.read_text())
                st.json(data, expanded=False)
            except Exception as e:
                st.error(f"Could not parse {jf.name}: {e}")

    if csv_files:
        import pandas as pd
        st.subheader("Benchmark CSV runs")
        pick = st.selectbox("Select run", [f.name for f in csv_files])
        df = pd.read_csv(ROOT / pick)
        st.dataframe(df, width="stretch")


# ============================================================================
# Page: Pipeline Explorer (stage-level tools)
# ============================================================================

def page_explorer():
    st.title("🔬 Pipeline Explorer")
    st.caption("Exercise individual pipeline stages without running the full workflow.")

    tab1, tab2, tab3 = st.tabs(["SHACL Validator", "Reranker Preview", "Abstention Gate"])

    with tab1:
        st.subheader("Validate a JSON-LD configuration against SHACL shapes")
        protocol = st.selectbox("Protocol shapes", list(PROTOCOLS.values()), key="shacl_proto")
        sample = {
            "@context": {"clarity": "https://clarity-system.io/ns/"},
            "@type": "clarity:ModbusDevice",
            "clarity:protocolConfig": {
                "clarity:registers": [
                    {"clarity:registerAddress": 128, "clarity:value": 0,
                     "clarity:functionCode": 6, "clarity:dataType": "UINT16"}
                ]
            },
        }
        text = st.text_area("JSON-LD", value=json.dumps(sample, indent=2), height=260)
        if st.button("Validate", key="shacl_btn"):
            try:
                payload = json.loads(text)
            except json.JSONDecodeError as e:
                st.error(f"Invalid JSON: {e}")
                return
            result = get_shacl_validator().validate(payload, protocol)
            if result.conforms:
                st.success("✅ Conforms: no SHACL violations")
            else:
                st.error(f"❌ {len(result.violations)} violation(s)")
                for v in result.violations:
                    st.code(v)

    with tab2:
        st.subheader("Score a query against candidate chunks with the cross-encoder")
        query = st.text_input("Query", value="Modbus register address for joint angles")
        cands = st.text_area(
            "Candidate chunks (one per line)",
            value=(
                "Registers 270 to 275 hold the joint angles in milli-radians.\n"
                "The robot arm should be stored at temperatures between 0 and 50 C.\n"
                "General purpose registers 128 to 255 are readable and writable."
            ),
            height=120,
        )
        if st.button("Rank", key="rank_btn"):
            lines = [c.strip() for c in cands.strip().splitlines() if c.strip()]
            from clarity.retrieval.hybrid_fusion import FusedResult
            fused = [
                FusedResult(chunk_id=str(i), text=c, source_path="manual", page_num=0,
                            chunk_type="text", rrf_score=0.0, dense_score=0.0,
                            sparse_score=0.0, graph_boost=0.0, metadata={})
                for i, c in enumerate(lines)
            ]
            ranked = get_reranker("cross-encoder/ms-marco-MiniLM-L-6-v2").rerank(
                query, fused, top_n=len(fused))
            import pandas as pd
            st.dataframe(pd.DataFrame(
                [{"rank": i + 1, "score": round(r.rerank_score, 4), "text": r.text}
                 for i, r in enumerate(ranked)]
            ), width="stretch", hide_index=True)

    with tab3:
        st.subheader("Simulate the two-stage abstention gate")
        c1, c2, c3 = st.columns(3)
        s_max = c1.slider("s_max (max rerank score)", 0.0, 1.0, 0.85, 0.01)
        iri_ratio = c2.slider("Unresolved IRI ratio", 0.0, 1.0, 0.10, 0.01)
        tau = c3.slider("Threshold τ", 0.0, 1.0, DEFAULT_TAU, 0.01)
        reasons = []
        if s_max < tau:
            reasons.append(f"Pre-LLM gate: s_max {s_max:.2f} < τ {tau:.2f}")
        if iri_ratio > 0.20:
            reasons.append(f"IRI gate: unresolved ratio {iri_ratio:.2f} > 0.20")
        if reasons:
            for r in reasons:
                st.warning(r)
            st.error("Decision: ABSTAIN (escalate to a human)")
        else:
            st.success("Decision: PROCEED")


# ============================================================================
# Page: About
# ============================================================================

def page_about():
    st.title("ℹ️ About CLARITY")
    st.markdown(
        """
CLARITY (Context-aware LLM-Assisted Retrieval and Intelligent Auto-configuraTion sYstem)
turns unstructured device documentation into validated, deployed device configurations.

**How a request flows through the system:**

1. **Ingest**: PDFs are parsed (text and tables), chunked at 512 tokens with 64-token
   overlap, embedded with BGE-M3, and indexed in an embedded vector store plus a BM25 index.
2. **Retrieve**: dense, sparse, and ontology-graph signals are fused with reciprocal
   rank fusion, then reranked by a cross-encoder with sigmoid-normalised scores.
3. **Gate**: a two-stage abstention gate refuses to proceed when retrieval confidence
   is below τ or ontology IRIs cannot be resolved, escalating to a human instead of guessing.
4. **Generate**: a local LLM (via Ollama) produces a JSON-LD configuration under
   schema-constrained decoding, with a four-step JSON repair fallback.
5. **Validate**: the configuration is checked against protocol-specific SHACL safety
   shapes; failures block deployment entirely.
6. **Deploy and verify**: a protocol deployer writes the configuration to the device
   (Modbus TCP, OPC UA, PROFIBUS, or generic fieldbus) and independently reads every
   value back to confirm it landed.
        """
    )
    st.graphviz_chart(
        """
digraph clarity {
    rankdir=LR;
    node [shape=box, style=rounded, fontsize=11];
    Docs [label="Device docs\\n(PDF upload)"];
    Ingest [label="Parse + chunk\\n+ embed + index"];
    Retrieve [label="Hybrid retrieval\\n(dense + BM25 + graph)\\n+ rerank"];
    Gate [label="Abstention gate\\n(s_max vs τ, IRI check)", color=orange];
    LLM [label="LLM generation\\n(JSON-LD, schema-locked)"];
    SHACL [label="SHACL safety\\nvalidation", color=orange];
    Deploy [label="Protocol deployer\\n(write + read-back)"];
    Device [label="Device\\n(real or simulated)", shape=cylinder];
    Human [label="Human expert", shape=ellipse];
    Docs -> Ingest -> Retrieve -> Gate -> LLM -> SHACL -> Deploy -> Device;
    Gate -> Human [label="abstain", style=dashed];
    SHACL -> Human [label="violation", style=dashed];
}
        """
    )
    st.markdown(
        """
**Safety properties enforced by the app:**
- No write ever happens unless SHACL validation passes.
- Reserved register addresses are hard-blocked in the deployer.
- Every deployed value is verified by an independent read-back.
- When evidence is insufficient the system abstains and escalates instead of guessing.
        """
    )


# ============================================================================
# Router
# ============================================================================

def main():
    _init_state()

    st.sidebar.title("⚙️ CLARITY")
    st.sidebar.caption("LLM-assisted industrial device auto-configuration")

    page = st.sidebar.radio(
        "Navigate",
        ["Auto-Configure", "System Health", "Run History", "Evaluation Results",
         "Pipeline Explorer", "About"],
    )

    st.sidebar.divider()
    kb = get_kb()
    st.sidebar.metric("Documents in KB", len(kb["docs"]))
    st.sidebar.metric("Chunks indexed", len(kb["chunks"]))
    ok_o, _ = _ping(f"{DEFAULT_OLLAMA}/api/tags", timeout=1.0)
    st.sidebar.markdown(f"**Ollama:** {'🟢 up' if ok_o else '🔴 down'}")
    st.sidebar.caption("Model default: " + DEFAULT_MODEL)

    if page == "Auto-Configure":
        page_autoconfigure()
    elif page == "System Health":
        page_health()
    elif page == "Run History":
        page_history()
    elif page == "Evaluation Results":
        page_evaluation()
    elif page == "Pipeline Explorer":
        page_explorer()
    else:
        page_about()


main()
