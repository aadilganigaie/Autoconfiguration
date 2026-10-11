#!/usr/bin/env python3
import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from clarity.config import ClarityConfig, DEFAULT_CONFIG
from clarity.pipeline.clarity_pipeline import ClarityPipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Ingest PDF device manuals into CLARITY knowledge base.")
    parser.add_argument("--input-dir", required=True, help="Directory containing PDF manuals.")
    parser.add_argument("--protocol", default="", choices=["modbus", "opcua", "profibus", "fieldbus", ""],
                        help="Protocol tag for all ingested documents.")
    parser.add_argument("--config", default=None, help="Path to JSON config file.")
    parser.add_argument("--recursive", action="store_true", help="Search subdirectories for PDFs.")
    args = parser.parse_args()

    config = DEFAULT_CONFIG
    if args.config:
        with open(args.config) as f:
            config_data = json.load(f)
        config = ClarityConfig(**config_data)

    input_dir = Path(args.input_dir)
    if not input_dir.exists():
        logger.error(f"Input directory does not exist: {input_dir}")
        sys.exit(1)

    pattern = "**/*.pdf" if args.recursive else "*.pdf"
    pdf_files = sorted(input_dir.glob(pattern))

    if not pdf_files:
        logger.warning(f"No PDF files found in {input_dir}")
        sys.exit(0)

    logger.info(f"Found {len(pdf_files)} PDF(s) to ingest.")

    pipeline = ClarityPipeline(config)
    total_chunks = 0

    for i, pdf_path in enumerate(pdf_files, 1):
        logger.info(f"[{i}/{len(pdf_files)}] Ingesting: {pdf_path.name}")
        try:
            n_chunks = pipeline.ingest_manual(str(pdf_path), protocol_tag=args.protocol)
            total_chunks += n_chunks
            logger.info(f"  -> {n_chunks} chunks indexed.")
        except Exception as e:
            logger.error(f"  -> Failed to ingest {pdf_path.name}: {e}")

    logger.info(f"Ingestion complete. Total chunks indexed: {total_chunks}")


if __name__ == "__main__":
    main()
