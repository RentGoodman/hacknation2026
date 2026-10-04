from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CANONICAL = Path("out/rules.json")
ALLOWED_NON_OUTPUT = {Path("starter pack/submission_templates/rules.json")}


def main() -> None:
    found = {
        path.relative_to(ROOT)
        for path in ROOT.rglob("rules.json")
        if ".git" not in path.parts and ".venv" not in path.parts and "node_modules" not in path.parts
    }
    unexpected = sorted(found - {CANONICAL} - ALLOWED_NON_OUTPUT)
    if not (ROOT / CANONICAL).is_file():
        raise SystemExit(f"missing canonical output: {CANONICAL}")
    if unexpected:
        raise SystemExit("competing rules.json output(s): " + ", ".join(map(str, unexpected)))
    print(f"canonical rules output: {CANONICAL}; no competing generated rules.json")


if __name__ == "__main__":
    main()
