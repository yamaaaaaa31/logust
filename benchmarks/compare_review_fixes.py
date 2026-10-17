"""Compare two installed release wheels, outside either source checkout.

Example:
    python benchmarks/compare_review_fixes.py BASELINE_PYTHON CANDIDATE_PYTHON results.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import subprocess
import tempfile
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--samples", type=int, default=7)
    parser.add_argument("--calls", type=int, default=300000)
    parser.add_argument("--baseline-commit", default="unspecified")
    parser.add_argument("--candidate-commit", default="unspecified")
    args = parser.parse_args()
    if args.samples < 1 or args.calls < 1:
        parser.error("--samples and --calls must be positive")
    script = Path(__file__).with_name("bench_review_fixes.py").resolve()
    paths = {"baseline": args.baseline.resolve(), "candidate": args.candidate.resolve()}
    raw: dict[str, list[dict]] = {label: [] for label in paths}
    with tempfile.TemporaryDirectory(prefix="logust-compare-") as directory:
        for index in range(args.samples):
            order = ["baseline", "candidate"]
            if index % 2:
                order.reverse()
            for label in order:
                completed = subprocess.run(
                    [str(paths[label]), str(script), "--calls", str(args.calls)],
                    cwd=directory,
                    capture_output=True,
                    text=True,
                    timeout=120,
                    check=True,
                )
                raw[label].append(json.loads(completed.stdout))
            print(f"{index + 1}/{args.samples}", flush=True)
    medians = {
        label: {
            case: statistics.median(sample["results"][case]["ns_per_call"] for sample in samples)
            for case in samples[0]["results"]
        }
        for label, samples in raw.items()
    }
    for baseline, candidate in zip(raw["baseline"], raw["candidate"], strict=True):
        assert baseline["results"].keys() == candidate["results"].keys()
        for case, before in baseline["results"].items():
            after = candidate["results"][case]
            assert before["calls"] == after["calls"], case
            assert before["fingerprint"] == after["fingerprint"], case
    ratios = {
        case: medians["candidate"][case] / medians["baseline"][case] for case in medians["baseline"]
    }
    result = {
        "baseline_commit": args.baseline_commit,
        "candidate_commit": args.candidate_commit,
        "script_sha256": hashlib.sha256(script.read_bytes()).hexdigest(),
        "samples": args.samples,
        "calls": args.calls,
        "comparison": "alternating release wheels; equal file/callback output fingerprints",
        "median_ns_per_call": medians,
        "ratios_after_over_before": ratios,
        "raw": raw,
    }
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"median_ns_per_call": medians, "ratios": ratios}, indent=2))


if __name__ == "__main__":
    main()
