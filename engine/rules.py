import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "dev_rules.json"
LOCAL_CANDIDATES = [ROOT / "out" / "rules.json"]
GIT_CANDIDATES = [("origin/main", "out/rules.json")]


def _parse(text):
    data = json.loads(text)
    return data["rules"] if isinstance(data, dict) else data


def _git_show(ref, path):
    try:
        return subprocess.run(["git", "-C", str(ROOT), "show", f"{ref}:{path}"], capture_output=True,
                              text=True, check=True).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def _load_text(fetch=True):
    for p in LOCAL_CANDIDATES:
        if p.exists():
            return p.read_text(), str(p.relative_to(ROOT)), False
    if fetch:
        subprocess.run(["git", "-C", str(ROOT), "fetch", "-q", "origin", "main"],
                       capture_output=True)
    for ref, path in GIT_CANDIDATES:
        text = _git_show(ref, path)
        if text:
            return text, f"{ref}:{path}", False
    return FIXTURE.read_text(), "engine/fixtures/dev_rules.json (TEST ONLY)", True


def load_rules(fetch=True):
    text, source, is_fixture = _load_text(fetch)
    return _parse(text), source, is_fixture


def load_rules_meta(fetch=True):
    text, source, is_fixture = _load_text(fetch)
    return _parse(text), {"rules_source": source, "rules_sha256": hashlib.sha256(text.encode()).hexdigest(),
                          "test_only_fixture": is_fixture}


def load_buildings():
    return json.loads((ROOT / "out" / "buildings.json").read_text())
