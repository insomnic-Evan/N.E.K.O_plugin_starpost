"""Run with official N.E.K.O. source on PYTHONPATH and a local Starpost test relay."""

import asyncio
import json
import logging
import os
import subprocess
from importlib import import_module
from pathlib import Path
from queue import Queue
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import AsyncMock

from plugin.core.source_imports import ensure_plugins_namespace, install_source_imports

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = (
    Path(os.environ["STARPOST_TEST_PACKAGE_ROOT"]) / "starpost" if "STARPOST_TEST_PACKAGE_ROOT" in os.environ else ROOT
)
ensure_plugins_namespace(PACKAGE.parent, logging.getLogger("starpost-tests"))
install_source_imports("plugins.starpost", PACKAGE)
StarpostPlugin = import_module("plugins.starpost").StarpostPlugin


async def exercise(root, relay):
    home = root / "account"
    os.environ["STARPOST_NEKO_HOME"] = str(home)
    origin = json.loads(relay.stdout.readline())["url"]

    def cli(*args):
        return json.loads(subprocess.check_output(["node", str(PACKAGE / "account.mjs"), *args], encoding="utf-8"))

    def peer(op, **kwargs):
        relay.stdin.write(json.dumps({"op": op, **kwargs}) + "\n")
        relay.stdin.flush()
        assert relay.stdout.readline().strip() == "{}"

    account = cli("register", "--character", "小星", "--server", origin, "--mode", "mixed")
    ident = account["botId"]
    secret = json.loads((home / "starpost-credential.json").read_text())["token"]
    assert account["registered"] and secret not in str(account)
    peer("befriend", target=ident)
    pushes = []
    allow = True

    def push(**kw):
        if allow:
            pushes.append(kw)
        return {"submitted": allow, "reason": None if allow else "backpressure"}

    ctx = SimpleNamespace(
        plugin_id="starpost",
        config_path=PACKAGE / "plugin.toml",
        logger=logging.getLogger("test"),
        message_queue=Queue(),
        push_message=push,
    )
    plugin = StarpostPlugin(ctx)
    plugin.config.dump = AsyncMock(return_value={"starpost": {"square_mode": "manual"}})
    try:
        result = await plugin.startup()
        assert plugin.list_llm_tools(), repr(result)
        panel = await plugin.binding_context()
        assert panel["botId"] == ident and "revealed" not in panel
        await plugin.show_binding(ui_token="not-from-the-panel")
        assert "revealed" not in await plugin.binding_context()
        reply = await plugin.show_binding(ui_token=panel["ui_token"])
        assert secret not in str(reply)
        assert (await plugin.binding_context())["revealed"]["credential"] == secret
        assert "revealed" not in await plugin.binding_context()
        await plugin.show_binding(ui_token=panel["ui_token"])
        assert "revealed" not in await plugin.binding_context()
        tool = plugin.list_llm_tools()[0]
        assert tool["role"] == "小星" and tool["name"] == "starpost_use"
        wrong = await plugin.agent_use("mobile", "send", '{"text":"wrong"}', _ctx={"lanlan_name": "另一位"})
        assert wrong.is_err()
        tools = await plugin._use("help", "show", "{}")
        families = {f["family"] for f in json.loads(tools["output"])["families"]}
        assert {"mobile", "werewolf", "mystery", "capsule", "message", "profile", "inbox"} <= families
        assert len(families) == 18
        reply = await plugin._use(
            "send", "send", json.dumps({"kind": "private", "target": "10001", "text": "来自小星"})
        )
        assert not reply.get("is_error"), reply
        peer("private", target=ident, text="收到来自好友的消息")
        await asyncio.sleep(4)
        history = await plugin._use("history", "read", '{"kind":"private","target":"10001"}')
        assert "来自小星" in history["output"] and "收到来自好友的消息" in history["output"]
        await plugin.deliver()
        peer("owner", target=ident, text="主人频道的消息")
        deadline = asyncio.get_running_loop().time() + 15
        # Refusal must leave the same first ready event queued for another timer tick.
        allow = False
        while asyncio.get_running_loop().time() < deadline:
            if await plugin.bridge.call("pull"):
                item = await plugin.bridge.call("pull")
                try:
                    await plugin.deliver()
                except RuntimeError:
                    pass
                assert (await plugin.bridge.call("pull"))["id"] == item["id"]
                break
            await asyncio.sleep(0.2)
        else:
            raise AssertionError("owner did not wake the client")
        allow = True
        await plugin.deliver()
        assert any("主人频道的消息" in str(m) and m["ai_behavior"] == "respond" for m in pushes), pushes
        assert all(m["target_lanlan"] == "小星" for m in pushes)
        assert secret not in str(pushes)
        assert (await plugin._use("werewolf", "rules", "{}"))["output"]
        await plugin.freeze()
        assert plugin.bridge is None and not plugin.list_llm_tools()
        await plugin.unfreeze()
        assert len(plugin.list_llm_tools()) == 1
        print(
            "PASS isolated account, 18 tool families, scoped SDK registration, chat, owner wake, delivery retry, freeze and resume."
        )
    finally:
        await plugin.shutdown()


if __name__ == "__main__":
    with TemporaryDirectory() as directory:
        relay = subprocess.Popen(
            ["node", str(ROOT / "tests/relay.mjs"), directory],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        try:
            asyncio.run(exercise(Path(directory), relay))
        finally:
            relay.stdin.close()
            try:
                relay.wait(timeout=6)
            except subprocess.TimeoutExpired:
                relay.kill()
                relay.wait()
