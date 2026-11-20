"""Extract only the MIT client runtime from the pinned published DSH npm archive."""

import hashlib
import json
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "runtime"
with tarfile.open(sys.argv[1]) as archive:

    def get(name):
        return archive.extractfile("package/" + name).read()

    meta = json.loads(get("package.json"))
    if (meta["name"], meta["version"], meta["starpostCoreVersion"]) != ("dsh-plugin-starpost", "0.3.2", "0.35.1"):
        raise ValueError("Unexpected upstream client version")
    for file in ["lib/core.mjs", "lib/ENV_PROMPT.md", "src/local.mjs", "LICENSE"]:
        target = ROOT / file
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(get(file))
    (ROOT / "package.json").write_text(
        json.dumps({k: meta[k] for k in ("name", "version", "starpostCoreVersion", "license", "type")}, indent=2)
        + "\n",
        encoding="utf-8",
    )
print("Starpost core", meta["starpostCoreVersion"], hashlib.sha256((ROOT / "lib/core.mjs").read_bytes()).hexdigest())
