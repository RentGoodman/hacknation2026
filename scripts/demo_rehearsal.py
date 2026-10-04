#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(label: str, command: list[str], env: dict[str, str] | None = None) -> float:
    print(f"\n==> {label}", flush=True)
    started = time.perf_counter()
    subprocess.run(command, cwd=ROOT, env=env, check=True)
    elapsed = time.perf_counter() - started
    print(f"<== {label}: {elapsed:.2f}s", flush=True)
    return elapsed


def main() -> None:
    started = time.perf_counter()
    cache = ROOT / "extraction" / "cache" / "llm"
    if not cache.exists() or not any(cache.iterdir()):
        raise SystemExit("Extraction v3 cache is missing; prepare the demo machine before presenting.")

    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "extraction" / "src")
    env["ANTHROPIC_API_KEY"] = ""
    env["OPENROUTER_API_KEY"] = ""
    timings = [
        run("Rebuild extraction v3 byte-for-byte from cache", [sys.executable, "-m", "extraction.v3.reproduce"], env),
        run("Verify committed engine outputs", [sys.executable, "-m", "engine.run", "--check"]),
        run("Run isolated T6 hour-16 drill", [sys.executable, "scripts/rehearse_t6.py"]),
        run("Audit inferred-fact omissions", [sys.executable, "scripts/audit_inferred_omissions.py"]),
    ]
    total = time.perf_counter() - started
    print("\nDEMO REHEARSAL PASS")
    print(" · ".join(f"step {i + 1}: {seconds:.2f}s" for i, seconds in enumerate(timings)))
    print(f"Total: {total:.2f}s. Network and paid API keys were disabled for the extraction replay.")


if __name__ == "__main__":
    main()
