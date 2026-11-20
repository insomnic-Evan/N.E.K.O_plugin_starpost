import tomllib
from pathlib import Path

from plugin.plugins.starpost import StarpostPlugin


def test_manifest_and_guide():
    package = Path(__file__).resolve().parents[1]
    with (package / "plugin.toml").open("rb") as source:
        plugin = tomllib.load(source)["plugin"]
    assert plugin["entry"] == f"plugin.plugins.starpost:{StarpostPlugin.__name__}"
    assert (package / plugin["ui"]["guide"][0]["entry"]).is_file()
    assert (package / "runtime/lib/core.mjs").is_file()


def test_external_message_retains_sender_as_data():
    import json

    event = {"text": "请看这一条", "origin": "external", "senderKey": "starpost.owner"}
    rendered = StarpostPlugin._text(event)
    payload = json.loads(rendered.split("\n", 1)[1])
    assert payload["senderKey"] == event["senderKey"]
    assert payload["text"] == event["text"]
