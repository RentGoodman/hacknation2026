import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from engine.run import build_outputs, evaluation_context as load_context, presented_lookups
from engine.verdict import verdicts_for_building


def verdicts(ctx, aid, d):
    return verdicts_for_building(ctx["buildings"][aid], ctx["rules"], d)


def all_verdicts(ctx, d):
    return {a: verdicts(ctx, a, d) for a in sorted(ctx["buildings"])}


def all_public_verdicts(ctx, d):
    return presented_lookups(ctx["buildings"], ctx["rules"], d)[0]


ROOT = Path(__file__).resolve().parents[2]
DATES = ["2025-12-31", "2026-01-02", "2026-10-01", "2027-07-02"]


@pytest.fixture(scope="module")
def ctx():
    return load_context(fetch=False)


def test_batch_lookup_ui_identical(ctx):
    src = (ROOT / "mockup" / "scripts" / "build-data.py").read_text()
    assert "from engine.run import evaluation_rules" in src and "erules=evaluation_rules()" in src
    from engine import lookup
    divergence = 0
    public_by_date = {d: all_public_verdicts(ctx, d) for d in DATES}
    for d in DATES:
        batch = all_verdicts(ctx, d)
        for aid in sorted(ctx["buildings"]):
            if verdicts(ctx, aid, d) != batch[aid]:
                divergence += 1
    for aid in ("A0001", "A0107", "A0279", "A0065"):
        for d in DATES:
            out = subprocess.run([sys.executable, "-m", "engine.lookup", "--address", aid, "--as-of", d, "--json"],
                                 cwd=ROOT, capture_output=True, text=True, check=True).stdout
            if json.loads(out)["lookups"] != public_by_date[d][aid]:
                divergence += 1
    committed = json.loads((ROOT / "out" / "lookups.json").read_text())
    batch = public_by_date[committed["as_of"]]
    divergence += sum(1 for aid in batch if batch[aid] != committed["lookups"].get(aid))
    assert divergence == 0


def test_two_runs_byte_identical():
    a, _ = build_outputs("2026-10-01", fetch=False)
    b, _ = build_outputs("2026-10-01", fetch=False)
    assert a == b


def test_byte_identical_across_hash_seeds():
    code = ("import hashlib,json;from engine.run import build_outputs;o,_=build_outputs('2026-10-01',fetch=False);"
            "print(hashlib.sha256(json.dumps(o,sort_keys=True).encode()).hexdigest())")
    outs = {subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, check=True,
                           env={**__import__("os").environ, "PYTHONHASHSEED": seed}).stdout for seed in ("1", "2")}
    assert len(outs) == 1
