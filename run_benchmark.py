#!/usr/bin/env python3
import argparse
import csv
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from clarity.config import DEFAULT_CONFIG
from clarity.evaluation.benchmark import ClarityBench
from clarity.pipeline.clarity_pipeline import ClarityPipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def print_metrics_table(metrics: dict) -> None:
    print("\n" + "=" * 60)
    print("CLARITY Benchmark Results")
    print("=" * 60)
    print(f"{'Metric':<35} {'Value':>10}")
    print("-" * 46)

    scalar_metrics = {k: v for k, v in metrics.items() if isinstance(v, (int, float))}
    for key, value in sorted(scalar_metrics.items()):
        if isinstance(value, float):
            print(f"{key:<35} {value:>10.4f}")
        else:
            print(f"{key:<35} {value:>10}")

    if "latency" in metrics:
        lat = metrics["latency"]
        print(f"{'latency_p50_ms':<35} {lat.get('p50', 0):>10.1f}")
        print(f"{'latency_p95_ms':<35} {lat.get('p95', 0):>10.1f}")
        print(f"{'latency_mean_ms':<35} {lat.get('mean', 0):>10.1f}")

    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Run CLARITY benchmark evaluation.")
    parser.add_argument("--bench-dir", default=None, help="Directory with benchmark JSON samples.")
    parser.add_argument("--use-synthetic", action="store_true",
                        help="Use built-in synthetic benchmark samples (no PDFs required).")
    parser.add_argument("--output", default="clarity_benchmark_results.csv", help="CSV output path.")
    parser.add_argument("--sample", action="append", metavar="SAMPLE_ID",
                        help="Run only this sample ID (can be repeated).")
    args = parser.parse_args()

    bench = ClarityBench()

    if args.use_synthetic:
        samples = bench.create_sample_benchmark()
        if args.sample:
            samples = [s for s in samples if s.sample_id in args.sample]
            logger.info(f"Filtered to {len(samples)} samples: {[s.sample_id for s in samples]}")
        else:
            logger.info(f"Using {len(samples)} synthetic benchmark samples.")
    elif args.bench_dir:
        bench_dir = Path(args.bench_dir)
        samples = bench.load_from_dir(bench_dir)
        logger.info(f"Loaded {len(samples)} samples from {bench_dir}")
    else:
        logger.error("Provide --bench-dir or --use-synthetic")
        sys.exit(1)

    pipeline = ClarityPipeline(DEFAULT_CONFIG)
    bench_results = bench.run(pipeline, samples)
    metrics = bench_results["metrics"]

    print_metrics_table(metrics)

    csv_rows = []
    for result in bench_results["results"]:
        csv_rows.append({
            "device_name": result.device_name,
            "protocol": result.protocol,
            "success": result.success,
            "abstained": result.abstained,
            "shacl_valid": result.shacl_valid,
            "deployed": result.deployed,
            "latency_ms": f"{result.latency_ms:.1f}",
            "retry_count": result.retry_count,
            "shacl_violations": len(result.shacl_violations),
            "safety_violations": len(result.safety_violations),
        })

    if csv_rows:
        with open(args.output, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=csv_rows[0].keys())
            writer.writeheader()
            writer.writerows(csv_rows)
        logger.info(f"Per-sample results saved to: {args.output}")


if __name__ == "__main__":
    main()
