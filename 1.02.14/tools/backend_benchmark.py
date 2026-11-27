# SPDX-License-Identifier: MIT
"""Repeatable synthetic AI-backend benchmark. Never reads credentials or uses network.

Run: vendor/python/python.exe tools/backend_benchmark.py --output reports/backend_benchmark.json
Each call traverses the AI request path using MockTransport SSE. Numbers measure
local request/prompt/history overhead, not real model, network, OCR or display latency.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import statistics
import sys
from tempfile import TemporaryDirectory
from time import perf_counter_ns

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
from nkc_galgame_translator.translation import TranslationEngine


def benchmark(iterations: int, glossary_entries: int) -> dict:
    """All API traffic is intercepted by httpx.MockTransport in this process."""
    stream = "".join("data: " + json.dumps(event, ensure_ascii=False) + "\n\n" for event in [
        {"choices": [{"delta": {"content": "\u8bf7\u6253\u5f00\u95e8\u3002"}, "finish_reason": None}]},
        {"choices": [{"delta": {}, "finish_reason": "stop"}]},
    ]) + "data: [DONE]\n\n"
    simulated_calls = 0

    def responder(request):
        nonlocal simulated_calls
        simulated_calls += 1
        return httpx.Response(200, text=stream, headers={"Content-Type": "text/event-stream"})

    with TemporaryDirectory(prefix="nkc_galgame_translator-offline-benchmark-") as directory:
        with httpx.Client(transport=httpx.MockTransport(responder)) as client:
            with TranslationEngine({"api_key": "offline-placeholder-never-transmitted",
                                    "base_url": "https://example.invalid/v1", "model": "simulated-ai",
                                    "unlimited_requests": True, "context_web_search": False},
                                   Path(directory) / "benchmark.sqlite3", client=client) as engine:
                for index in range(glossary_entries):
                    engine.set_term("benchmark", "en", "zh-Hans", f"Item{index}", f"\u7269\u54c1{index}")
                engine.translate("benchmark", "en", "zh-Hans", "Please open the door.")
                elapsed_ms = []
                for _ in range(iterations):
                    start = perf_counter_ns()
                    result = engine.translate("benchmark", "en", "zh-Hans", "Please open the door.")
                    elapsed_ms.append((perf_counter_ns() - start) / 1_000_000)
                    assert result == "\u8bf7\u6253\u5f00\u95e8\u3002"
                stats = engine.get_stats()
                assert simulated_calls == iterations + 1
                assert stats["session_requests"] == iterations + 1
                assert stats["cache_hits"] == 0
    elapsed_ms.sort()
    return {
        "benchmark": "synthetic AI repeated-request local overhead (MockTransport SSE)",
        "utc_timestamp": datetime.now(timezone.utc).isoformat(),
        "python_version": platform.python_version(),
        "platform": platform.system() + " " + platform.machine(),
        "network_used": False,
        "credentials_loaded": False,
        "simulated_api_calls": simulated_calls,
        "warmup_requests": 1,
        "measured_requests": iterations,
        "stored_reference_entries": glossary_entries,
        "completed_result_cache_used": False,
        "p50_ms": round(statistics.median(elapsed_ms), 6),
        "p95_ms": round(elapsed_ms[min(len(elapsed_ms) - 1, int(len(elapsed_ms) * 0.95))], 6),
        "p99_ms": round(elapsed_ms[min(len(elapsed_ms) - 1, int(len(elapsed_ms) * 0.99))], 6),
        "mean_ms": round(statistics.mean(elapsed_ms), 6),
        "max_ms": round(max(elapsed_ms), 6),
        "limitation": "Synthetic SSE has no network/model waiting time. This measures prompt construction, request parsing and history storage only; it is not translation speed, in-flight coalescing, OCR, or overlay latency. Every completed repeat makes a new mocked AI request.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=200)
    parser.add_argument("--glossary-entries", type=int, default=1000,
                        help="Historical terminology references; never a local translation route")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not 1 <= args.iterations <= 1_000_000 or not 0 <= args.glossary_entries <= 5000:
        parser.error("iterations must be 1..1000000 and glossary-entries 0..5000")
    result = benchmark(args.iterations, args.glossary_entries)
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
