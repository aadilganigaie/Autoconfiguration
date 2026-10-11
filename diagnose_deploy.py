"""Quick diagnostic: show what JSON-LD was generated and why deploy failed."""
import sys
import json
sys.path.insert(0, "/home/aadil.ganie/Aadil/Autoconfiguration")

from clarity.config import DEFAULT_CONFIG
from clarity.pipeline.clarity_pipeline import ClarityPipeline
from clarity.evaluation.benchmark import _SYNTHETIC_SAMPLES

pipe = ClarityPipeline(DEFAULT_CONFIG)

# Test only TH200 (modbus) and XYZ (unknown)
for sample in _SYNTHETIC_SAMPLES:
    if sample.sample_id not in ("syn_001", "syn_005_abstain"):
        continue
    print(f"\n{'='*60}")
    print(f"Sample: {sample.sample_id} — {sample.device_name} ({sample.protocol})")
    result = pipe.configure_device(
        device_name=sample.device_name,
        manual_path=None,
        target_protocol=sample.protocol,
        device_description=sample.device_description,
    )
    print(f"success={result.success}, abstained={result.abstained}, shacl_valid={result.shacl_valid}, deployed={result.deployed}")
    if result.abstention_reason:
        print(f"abstention_reason: {result.abstention_reason}")
    if result.deploy_errors:
        print(f"deploy_errors: {result.deploy_errors}")
    if result.jsonld_config:
        print(f"JSON-LD (top-level keys): {list(result.jsonld_config.keys())}")
        proto_cfg = result.jsonld_config.get("clarity:protocolConfig")
        if proto_cfg:
            print(f"  protocolConfig keys: {list(proto_cfg.keys())}")
        else:
            print("  NO clarity:protocolConfig found!")
            # Show all keys to see where params ended up
            print(f"  Full JSON-LD: {json.dumps(result.jsonld_config, indent=2)[:2000]}")
