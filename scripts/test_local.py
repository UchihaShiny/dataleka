"""Run each regression in isolation; never load real .env. No warehouse/ingestion commands."""

import os
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
env = {**os.environ, "PYTHON_DOTENV_DISABLED": "1"}
env.pop("DATAE_MODE", None)
results = []
for path in sorted((root / "tests").glob("test_*.py")):
    result = subprocess.run(
        [sys.executable, str(path)], cwd=root, env=env, capture_output=True, text=True
    )
    print(f"{path.name}: {'PASS' if result.returncode == 0 else 'FAIL'}", flush=True)
    if result.returncode:
        print(result.stdout)
        print(result.stderr)
    results.append(result.returncode)
print(f"{len(results) - sum(bool(r) for r in results)}/{len(results)} suites passed")
sys.exit(any(results))
