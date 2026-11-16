"""Compare installed release wheels using APIs shared by 0.5.0 and 0.6.0.

Run outside either checkout. Every worker validates output after timing; the
parent retains all independent process results, including slower cases.
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
import platform
import re
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

CASES = (
    "message",
    "default",
    "kwargs",
    "module",
    "bound_small",
    "bound_large",
    "bound_large_extra",
    "json",
    "json_escaped",
    "json_bound",
    "callable",
    "callable_json",
    "filter",
    "patcher",
    "callback",
    "custom_level",
    "unicode",
    "long_message",
    "markup_color",
    "markup_strip",
    "late_markup",
    "console",
    "enqueue",
    "rotation",
    "opt_enabled",
    "opt_args",
    "opt_lazy",
    "suppressed",
    "suppressed_lazy",
    "suppressed_exception",
    "suppressed_opt_exception",
    "active_exception",
)


def worker(calls: int) -> dict:
    import logust
    import logust._logust as native
    from logust import Logger, LogLevel
    from logust._logust import PyLogger

    if Path(sys.prefix) not in Path(logust.__file__).parents:
        raise RuntimeError(f"Expected an installed wheel, imported {logust.__file__}")
    results = {}
    with tempfile.TemporaryDirectory(prefix="logust-release-") as directory:
        for case in CASES:
            logger = logust.logger if case == "module" else Logger(PyLogger(LogLevel.Trace))
            logger.remove()
            path = Path(directory) / f"{case}.log"
            seen = []
            record_seen = []
            options = {"format": "{message}"}
            if case in ("default", "module"):
                options = {}
            if case.startswith("json") or case == "callable_json":
                options["serialize"] = True
            if case == "enqueue":
                options["enqueue"] = True
            if case == "rotation":
                options["rotation"] = "10 KB"
            if case == "markup_color":
                options["colorize"] = True
            if case == "filter":

                def keep(record):
                    record_seen.append(str(record["message"]))
                    return True

                options["filter"] = keep
            if case.startswith("suppressed"):
                options["level"] = "CRITICAL"
            target = (
                seen.append
                if case in ("callable", "callable_json", "active_exception")
                or case.startswith("suppressed")
                else path
            )
            console_backup = None
            if case == "console":
                console_backup = os.dup(2)
                with path.open("w") as stream:
                    os.dup2(stream.fileno(), 2)
                target = sys.__stderr__
                options["colorize"] = False
            logger.add(target, **options)
            if case in ("bound_small", "json_bound"):
                logger = logger.bind(user_id=123, session="abc")
            if case in ("bound_large", "bound_large_extra"):
                logger = logger.bind(payload=list(range(1000)))
            if case == "patcher":

                def patch(record):
                    record["extra"]["patched"] = True

                logger = logger.patch(patch)
            if case == "callback":
                logger.add_callback(lambda record: record_seen.append(str(record["message"])))
            if case == "custom_level":
                logger.level("RELEASEBENCH", no=62, color="blue")

            expected = "payload"
            if case == "unicode":
                expected = "記録 café 🦀"
            if case == "long_message":
                expected = "x" * 4096
            if case == "json_escaped":
                expected = 'quote=" tab=\t newline=\n slash=\\ 記録'
            text = expected
            if case in ("markup_color", "markup_strip"):
                text = "<red>payload</red>"
            if case == "late_markup":
                text = "x" * 4096 + "<red>payload</red>"
                expected = "x" * 4096 + "payload"

            opt = (
                logger.opt(lazy=True)
                if case in ("opt_lazy", "suppressed_lazy")
                else logger.opt(exception=True)
                if case == "suppressed_opt_exception"
                else logger.opt()
            )

            def forbidden():
                raise AssertionError("Suppressed lazy value was evaluated")

            if case == "kwargs":
                expected = "payload 1"

                def emit():
                    logger.info("payload {value}", value=1)
            elif case == "module":

                def emit():
                    logust.info(text)
            elif case == "bound_large_extra":

                def emit():
                    logger.info(text, event=1)
            elif case == "custom_level":

                def emit():
                    logger.log("RELEASEBENCH", text)
            elif case == "opt_enabled":

                def emit():
                    opt.info(text)
            elif case in ("opt_args", "opt_lazy"):
                expected = "payload 1"

                def emit():
                    opt.info("payload {}", (lambda: 1) if case == "opt_lazy" else 1)
            elif case == "suppressed_lazy":

                def emit():
                    opt.debug("payload {}", forbidden)
            elif case == "suppressed_opt_exception":

                def emit():
                    opt.error(text)
            elif case in ("active_exception", "suppressed_exception"):

                def emit():
                    logger.exception(text)
            elif case == "suppressed":

                def emit():
                    logger.debug(text)
            else:

                def emit():
                    logger.info(text)

            count = (
                min(calls, 2000)
                if case in ("bound_large_extra", "json_bound", "long_message", "late_markup")
                else min(calls, 500)
                if "exception" in case
                else calls
            )
            warmup = 100
            timings = []
            try:
                try:
                    raise ValueError("release benchmark exception")
                except ValueError:
                    for _ in range(warmup):
                        emit()
                    logger.complete()
                    gc_was_enabled = gc.isenabled()
                    gc.disable()
                    try:
                        for _ in range(3):
                            start = time.perf_counter_ns()
                            for _ in range(count):
                                emit()
                            logger.complete()
                            timings.append((time.perf_counter_ns() - start) / count)
                    finally:
                        if gc_was_enabled:
                            gc.enable()
            finally:
                logger.remove()
                if console_backup is not None:
                    os.dup2(console_backup, 2)
                    os.close(console_backup)

            total = warmup + count * 3
            if case.startswith("suppressed"):
                assert seen == [], case
                normalized = []
            else:
                if case in ("callable", "callable_json", "active_exception"):
                    output = seen
                elif case == "rotation":
                    output = [
                        line
                        for p in sorted(Path(directory).glob("rotation*.log"))
                        for line in p.read_text().splitlines()
                    ]
                else:
                    output = path.read_text().splitlines()
                assert len(output) == total, (case, len(output), total)
                normalized = []
                for line in output:
                    if case.startswith("json") or case == "callable_json":
                        obj = json.loads(line)
                        assert obj["message"] == expected and obj["level"] == "INFO", (case, obj)
                        if case == "json_bound":
                            assert obj["extra"] == {"user_id": 123, "session": "abc"}
                    elif case == "active_exception":
                        assert (
                            expected in line and "ValueError: release benchmark exception" in line
                        )
                    elif case in ("default", "module"):
                        assert line.endswith(" - " + expected), (case, line)
                    else:
                        plain = re.sub(r"\x1b\[[0-9;]*m", "", line)
                        assert plain == expected, (case, plain[:100])
                        if case == "markup_color":
                            assert "\x1b[" in line
                    normalized.append(expected)
                if case in ("filter", "callback"):
                    assert record_seen == [expected] * total
            results[case] = {
                "calls_per_sample": count,
                "warmup_calls": warmup,
                "sample_ns_per_call": timings,
                "median_ns_per_call": statistics.median(timings),
                "validated_outputs": len(normalized),
                "semantic_sha256": hashlib.sha256(
                    json.dumps(normalized, ensure_ascii=False).encode()
                ).hexdigest(),
            }
    return {
        "python": sys.version,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "package": logust.__file__,
        "version": logust.__version__,
        "native": native.__file__,
        "native_sha256": hashlib.sha256(Path(native.__file__).read_bytes()).hexdigest(),
        "results": results,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", nargs="?", type=Path)
    parser.add_argument("candidate", nargs="?", type=Path)
    parser.add_argument("output", nargs="?", type=Path)
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--processes", type=int, default=6)
    parser.add_argument("--calls", type=int, default=20000)
    args = parser.parse_args()
    if args.calls < 1 or args.processes < 1:
        parser.error("counts must be positive")
    if args.worker:
        print(json.dumps(worker(args.calls)))
        return
    if not all((args.baseline, args.candidate, args.output)):
        parser.error("baseline, candidate and output are required")
    raw = {"baseline": [], "candidate": []}
    script = Path(__file__).resolve()
    env = dict(os.environ, PYTHONHASHSEED="0")
    env.pop("PYTHONPATH", None)
    with tempfile.TemporaryDirectory(prefix="logust-release-driver-") as cwd:
        for index in range(args.processes):
            order = ["baseline", "candidate"] if index % 2 == 0 else ["candidate", "baseline"]
            for label in order:
                interpreter = getattr(args, label).absolute()
                run = subprocess.run(
                    [str(interpreter), str(script), "--worker", "--calls", str(args.calls)],
                    cwd=cwd,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=300,
                )
                if run.returncode:
                    raise RuntimeError(f"{label}: {run.stderr[-5000:]}")
                raw[label].append(json.loads(run.stdout))
            print(f"{index + 1}/{args.processes} pairs complete", flush=True)
    summary = {}
    for case in CASES:
        before = [v["results"][case]["median_ns_per_call"] for v in raw["baseline"]]
        after = [v["results"][case]["median_ns_per_call"] for v in raw["candidate"]]
        pairs = []
        for old, new, a, b in zip(raw["baseline"], raw["candidate"], before, after):
            assert (
                old["results"][case]["semantic_sha256"] == new["results"][case]["semantic_sha256"]
            ), case
            pairs.append((b / a - 1) * 100)
        ratio = statistics.median(after) / statistics.median(before)
        # Describe repeated >=5% slowdowns separately from mixed/small changes.
        slower = sum(value >= 5 for value in pairs)
        summary[case] = {
            "baseline_ns": statistics.median(before),
            "candidate_ns": statistics.median(after),
            "elapsed_change_percent": (ratio - 1) * 100,
            "speedup": 1 / ratio,
            "paired_changes_percent": pairs,
            "pairs_faster": sum(v < 0 for v in pairs),
            "pairs_at_least_5_percent_slower": slower,
            "repeated_slowdown": ratio >= 1.05 and slower >= max(1, args.processes - 1),
        }
    result = {
        "script_sha256": hashlib.sha256(script.read_bytes()).hexdigest(),
        "processes_per_head": args.processes,
        "calls": args.calls,
        "nested_samples_per_process": 3,
        "summary": summary,
        "raw": raw,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
