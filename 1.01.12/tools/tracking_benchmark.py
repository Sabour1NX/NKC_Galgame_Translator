# SPDX-License-Identifier: MIT
"""Reproducible offline benchmark of 32 OCR object associations.

Run: python tools/tracking_benchmark.py --samples 11
Only ObjectTracker.update is timed. No credentials, network, OCR or UI are used.
Python scoring threads are subject to the GIL; this is not a CPU speedup test.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import statistics
import sys
from time import perf_counter_ns

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nkc_galgame_translator.tracking import ObjectTracker


def observations(texts: list[str]) -> list[dict]:
    return [
        {"text": text, "x": 20, "y": index * 60, "w": 320, "h": 24,
         "bg": [0, 0, 0], "fg": [255, 255, 255]}
        for index, text in enumerate(texts)
    ]


def scenarios() -> list[tuple[str, str, list[str], list[str]]]:
    ordinary = [f"Action {index}: open the door." for index in range(32)]
    repetitive = [f"Actor {index}: " + "abc " * 180 + f" end {index}."
                  for index in range(32)]
    return [
        ("ordinary_word_edit", "Replace 'open' with 'close' in every ordinary text.",
         ordinary, [text.replace("open", "close") for text in ordinary]),
        ("repetitive_append", "Append '!' to every repetitive paragraph.",
         repetitive, [text + "!" for text in repetitive]),
        ("repetitive_both_edges", "Prepend 'New ' and append '!' to every repetitive paragraph.",
         repetitive, ["New " + text + "!" for text in repetitive]),
    ]


def benchmark(samples: int, workers: int) -> dict:
    cases = []
    for name, description, before, after in scenarios():
        initial_lines, updated_lines = observations(before), observations(after)
        elapsed_ms = []
        for _ in range(samples):
            # Independent trackers keep revisions and input states identical in
            # every sample. The first scored update activates the worker pool.
            with ObjectTracker(workers=workers, max_tracks=32) as tracker:
                initial = tracker.update(initial_lines)
                started = perf_counter_ns()
                latest = tracker.update(updated_lines)
                elapsed_ms.append((perf_counter_ns() - started) / 1_000_000)
                expected_ids = [track.track_id for track in initial.tracks]
                if (len(latest.tracks) != 32
                        or [track.track_id for track in latest.tracks] != expected_ids
                        or any(track.revision != 2 for track in latest.tracks)
                        or sorted(latest.changed_ids) != sorted(expected_ids)
                        or latest.removed_ids):
                    raise RuntimeError(f"Tracker identity/revision check failed: {name}")
        cases.append({
            "scenario": name,
            "description": description,
            "source_example": before[0],
            "source_character_count_range": [min(map(len, before)), max(map(len, before))],
            "target_character_count_range": [min(map(len, after)), max(map(len, after))],
            "sample_count": samples,
            "median_ms": round(statistics.median(elapsed_ms), 6),
            "max_ms": round(max(elapsed_ms), 6),
            "min_ms": round(min(elapsed_ms), 6),
            "samples_ms": [round(value, 6) for value in elapsed_ms],
            "all_ids_preserved": True,
            "all_changed_revisions_equal_2": True,
        })
    gil_probe = getattr(sys, "_is_gil_enabled", None)
    return {
        "benchmark": "32-object OCR region association; independent trackers",
        "utc_timestamp": datetime.now(timezone.utc).isoformat(),
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "gil_enabled": gil_probe() if gil_probe else None,
        "tracker_source_sha256": hashlib.sha256(
            (ROOT / "nkc_galgame_translator" / "tracking.py").read_bytes()).hexdigest(),
        "workers": workers,
        "objects_per_update": 32,
        "possible_candidate_pairs": 1024,
        "sample_count_per_scenario": samples,
        "network_used": False,
        "credentials_loaded": False,
        "layout": {"x": 20, "row_spacing": 60, "width": 320, "height": 24},
        "measurement_scope": (
            "Second update only: observation normalization, candidate scoring, assignment, "
            "snapshot publication and initial scoring worker activation. Excludes tracker "
            "construction, initial seed update, correctness checks and tracker close."
        ),
        "limitations": [
            "Sparse stationary rectangles permit early distance pruning; this is not a dense overlap benchmark.",
            "No screen capture, OCR, real API, streaming or overlay display latency is measured.",
            "Python CPU scoring is constrained by the GIL; threads do not imply multicore speedup.",
            "Timing includes OS scheduling and varies by machine; no timing thresholds are asserted.",
        ],
        "scenarios": cases,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=11)
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=2)
    parser.add_argument("--output", type=Path, default=ROOT / "reports" / "tracking-benchmark.json")
    args = parser.parse_args()
    if not 1 <= args.samples <= 1000:
        parser.error("samples must be 1..1000")
    result = benchmark(args.samples, args.workers)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for case in result["scenarios"]:
        print(f"{case['scenario']}: n={case['sample_count']}, "
              f"median={case['median_ms']:.3f} ms, max={case['max_ms']:.3f} ms")
    print(f"Report: {args.output}")


if __name__ == "__main__":
    main()
