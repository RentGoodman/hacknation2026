import os
import subprocess
import sys
from pathlib import Path

here = Path(__file__).resolve().parent
extras = ["--extra", "anthropic"] if os.environ.get("LLM_BACKEND") == "api" else []
cmd = ["uv", "run", "--quiet", "--project", str(here), *extras, "python", "-m", "extraction.ingest_new", *sys.argv[1:]]
sys.exit(subprocess.run(cmd, cwd=here.parent, env={**os.environ, "PYTHONPATH": str(here / "src")}).returncode)
