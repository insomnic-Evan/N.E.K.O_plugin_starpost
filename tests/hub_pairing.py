"""Verify user-facing CLI pairing states with an isolated Hub and relay fixture."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
from secrets import token_hex
import subprocess
from tempfile import TemporaryDirectory
from threading import Thread

package = Path(os.environ.get("STARPOST_TEST_PACKAGE_ROOT", Path(__file__).resolve().parents[1])) / "starpost"
state = {"approved": False, "primary": False}
access, poll_secret = token_hex(32), token_hex(32)


class Pairing(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path == "/hub/info":
            result = {"issuer": origin, "service": "starpost"}
        elif self.path == "/v1/pairings":
            state["installation"] = body["installationId"]
            result = {"pairingId": "local-pair", "challenge": "local-challenge", "pollingSecret": poll_secret,
                      "shortCode": "LOCAL", "verificationUri": origin + "/?pair=local-pair"}
        elif self.path == "/v1/pairings/prove":
            assert body["pollingSecret"] == poll_secret and body["signature"].count(".") == 2
            result = {}
        elif self.path == "/v1/pairings/poll":
            assert body["pollingSecret"] == poll_secret
            result = {"status": "approved" if state["approved"] else "pending", "issuer": origin, "audience": "starpost",
                      "installationId": state["installation"], "subject": "local-bot", "accessToken": access}
        elif self.path in ("/hub/connect", "/hub/session"):
            assert body["token"] == access
            result = {"botId": "10123", "subject": "local-bot", "issuer": origin, "isPrimary": state["primary"],
                      "expiresAt": 4102444800000}
        else:
            self.send_error(404)
            return
        data = json.dumps({"ok": True, "result": result}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


with ThreadingHTTPServer(("127.0.0.1", 0), Pairing) as server, TemporaryDirectory() as directory:
    origin = f"http://127.0.0.1:{server.server_port}"
    Thread(target=server.serve_forever, daemon=True).start()

    def cli(*args):
        output = subprocess.check_output(["node", str(package / "account.mjs"), *args],
                                         env={**os.environ, "STARPOST_NEKO_HOME": directory}, timeout=15)
        assert access.encode() not in output and poll_secret.encode() not in output
        return json.loads(output)

    try:
        start = ("hub-login", "--character", "小星", "--server", origin, "--hub", origin)
        assert cli(*start)["pairing"]["shortCode"] == "LOCAL"
        assert not cli("hub-cancel").get("pairing")
        assert cli(*start)["pairing"]["verificationUri"] == origin + "/?pair=local-pair"
        assert cli("hub-complete")["pairingStatus"] == "pending"
        state["approved"] = True
        assert cli("hub-complete")["pairingStatus"] == "awaiting_primary"
        assert not cli("status")["registered"]
        state["primary"] = True
        assert cli("hub-complete")["pairingStatus"] == "connected"
        status = cli("status")
        assert status["botId"] == "10123" and status["hub"] == "hub" and status["registered"]
        print("PASS pairing, cancellation, approval, primary selection, persistence and CLI credential redaction.")
    finally:
        server.shutdown()

