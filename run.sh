#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

serve=0
[[ "${1:-}" == "--serve" ]] && serve=1

step() { printf '\n==> %s\n' "$1"; }

step "1/7 Buildings: out/buildings.json (Census responses cached in buildings/cache/)"
python3 -m buildings.run

step "2/7 Engine: out/lookups.json, out/changes.json, out/engine_run.json, out/voi.json"
python3 -m engine.rule_refs
python3 -m engine.run
python3 -m engine.voi

step "3/7 Independent audit of the outputs, and of recomputed results at each test date"
python3 -m engine.audit --as-of 2025-12-31 2026-01-02 2027-07-02
python3 scripts/audit_inferred_omissions.py --json out/inferred_omissions.json

step "4/7 Mockup data built from out/ and checked"
python3 mockup/scripts/build-data.py
python3 mockup/scripts/check-data.py
(cd mockup && npm run --silent check)

step "5/7 README numbers"
python3 scripts/update_readme_numbers.py

step "6/7 Tests (engine + buildings + llm backend)"
if python3 -c "import pytest, jsonschema" 2>/dev/null; then
  python3 -m pytest -q engine/tests buildings/tests tests
elif command -v uv >/dev/null; then
  uv run --no-project --with pytest --with jsonschema python -m pytest -q engine/tests buildings/tests tests
else
  echo "pytest not found: pip install pytest jsonschema (or install uv)"; exit 1
fi

step "7/7 Done. Changed outputs:"
git status --short out/ mockup/dist/data/ README.md || true

if [[ $serve == 1 ]]; then
  step "Starting mockup at http://127.0.0.1:4173 (Ctrl+C to stop)"
  cd mockup && exec npm run --silent dev
fi
