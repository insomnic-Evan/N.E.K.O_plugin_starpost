"""Exercise the installed entrypoint in an official PluginHost child process."""

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from plugin.core.host import PluginHost

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

HERE = Path(__file__).resolve().parent
PACKAGE = (
    Path(os.environ["STARPOST_TEST_PACKAGE_ROOT"]) / "starpost"
    if "STARPOST_TEST_PACKAGE_ROOT" in os.environ
    else HERE.parent
)


async def check(directory):
    os.environ["STARPOST_NEKO_HOME"] = str(directory / "account")
    relay = subprocess.Popen(
        ["node", str(HERE / "relay.mjs"), str(directory)],
        text=True,
        encoding="utf-8",
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
    )
    host = None
    try:
        url = json.loads(relay.stdout.readline())["url"]
        subprocess.run(
            ["node", str(PACKAGE / "account.mjs"), "register", "--character", "小星", "--server", url],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        host = PluginHost(
            "starpost", "plugin.plugins.starpost:StarpostPlugin", PACKAGE / "plugin.toml", source_only=True
        )
        await host.start(startup_timeout=25, startup_failure="abort")
        result = await host.trigger(
            "__llm_tool__starpost_use", {"family": "werewolf", "action": "rules", "argsJson": "{}"}, timeout=12
        )
        assert "dailyLimit" in str(result), result
        entry = await host.trigger(
            "starpost_use",
            {"family": "help", "action": "show", "argsJson": "{}", "_ctx": {"lanlan_name": "小星"}},
            timeout=12,
        )
        assert "families" in str(entry), entry
        print("PASS official PluginHost loads, starts and invokes main-dialogue and NekoClaw tools.")
    finally:
        if host and host.process.is_alive():
            await host.shutdown(timeout=8)
        relay.stdin.close()
        relay.wait(timeout=10)


if __name__ == "__main__":
    with TemporaryDirectory() as root:
        asyncio.run(check(Path(root)))
