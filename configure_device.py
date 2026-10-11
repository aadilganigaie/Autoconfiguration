#!/usr/bin/env python3
import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from clarity.config import DEFAULT_CONFIG
from clarity.pipeline.closed_loop import ClosedLoopController

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(
        description="Auto-configure an industrial device from a PDF manual using CLARITY."
    )
    parser.add_argument("--manual", default=None, help="Path to device PDF manual.")
    parser.add_argument("--device", required=True, help="Device name (e.g. 'Siemens S7-1200').")
    parser.add_argument("--protocol", required=True,
                        choices=["modbus", "opcua", "profibus", "fieldbus"],
                        help="Target industrial protocol.")
    parser.add_argument("--output", default=None, help="Output path for JSON-LD config file.")
    parser.add_argument("--description", default="", help="Optional device description.")
    parser.add_argument("--max-retries", type=int, default=3, help="Max closed-loop retry attempts.")
    args = parser.parse_args()

    controller = ClosedLoopController(DEFAULT_CONFIG)

    logger.info(f"Configuring device: {args.device} | Protocol: {args.protocol}")
    if args.manual:
        logger.info(f"Manual: {args.manual}")

    result = controller.configure_with_retry(
        device_name=args.device,
        manual_path=args.manual,
        protocol=args.protocol,
        description=args.description,
        max_retries=args.max_retries,
    )

    print("\n" + "=" * 60)
    print("CLARITY Configuration Result")
    print("=" * 60)
    print(f"Device:         {result.device_name}")
    print(f"Protocol:       {result.protocol}")
    print(f"Success:        {result.success}")
    print(f"Abstained:      {result.abstained}")
    print(f"SHACL Valid:    {result.shacl_valid}")
    print(f"Deployed:       {result.deployed}")
    print(f"Retry Count:    {result.retry_count}")
    print(f"Latency:        {result.latency_ms:.1f} ms")

    if result.abstention_reason:
        print(f"\nAbstention Reason: {result.abstention_reason}")

    if result.shacl_violations:
        print(f"\nSHACL Violations ({len(result.shacl_violations)}):")
        for v in result.shacl_violations[:5]:
            print(f"  - {v}")

    if result.safety_violations:
        print(f"\nSAFETY VIOLATIONS ({len(result.safety_violations)}):")
        for v in result.safety_violations:
            print(f"  !! {v}")

    if result.jsonld_config and not result.jsonld_config.get("abstained"):
        output_path = args.output or f"{args.device.replace(' ', '_')}_{args.protocol}_config.jsonld"
        with open(output_path, "w") as f:
            json.dump(result.jsonld_config, f, indent=2)
        print(f"\nJSON-LD config saved to: {output_path}")

    sys.exit(0 if result.success else 1)


if __name__ == "__main__":
    main()
