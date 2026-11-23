"""Refresh the bundled MIT runtime from the pinned DSH npm archive."""
import hashlib
import json
import sys
import tarfile
from pathlib import Path

root = Path(__file__).parent / "runtime"
with tarfile.open(sys.argv[1]) as archive:
    def read(name):
        return archive.extractfile("package/" + name).read()
    meta = json.loads(read("package.json"))
    if (meta["name"], meta["version"], meta["starpostCoreVersion"]) != ("dsh-plugin-starpost", "0.5.0", "0.36.0"):
        raise ValueError("Unexpected upstream client version")
    for name in ["lib/core.mjs", "lib/ENV_PROMPT.md", "src/local.mjs", "web/fields.mjs", "LICENSE"]:
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(read(name))
    (root / "package.json").write_text(json.dumps({k: meta[k] for k in ("name", "version", "starpostCoreVersion", "license", "type")}, indent=2) + chr(10), encoding="utf-8")
print("Starpost core", meta["starpostCoreVersion"], hashlib.sha256((root/"lib/core.mjs").read_bytes()).hexdigest())
