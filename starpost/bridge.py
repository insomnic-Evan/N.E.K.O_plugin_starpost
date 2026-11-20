"""Thread-safe RPC to the private Node worker across N.E.K.O. lifecycle event loops."""
import asyncio
from concurrent.futures import Future
import itertools
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading


class Bridge:
    def __init__(self, directory):
        node = shutil.which("node")
        if not node:
            raise RuntimeError("请安装 Node.js 22.16 或更新的 LTS，并重启 N.E.K.O.")
        self.process = subprocess.Popen(
            [node, str(Path(__file__).with_name("worker.mjs")), str(directory)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8", bufsize=1,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
        )
        self.lock = threading.Lock()
        self.waiters = {}
        self.ids = itertools.count(1)
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self):
        try:
            for line in self.process.stdout:
                reply = json.loads(line)
                with self.lock:
                    waiter = self.waiters.pop(reply["id"], None)
                if waiter:
                    if "error" in reply:
                        waiter.set_exception(RuntimeError(reply["error"]))
                    else:
                        waiter.set_result(reply["result"])
        finally:
            with self.lock:
                remaining = list(self.waiters.values())
                self.waiters.clear()
            for waiter in remaining:
                waiter.set_exception(RuntimeError("星邮运行端已退出，请检查 Node.js 版本并重启插件。"))

    async def call(self, op, args=None):
        request_id = next(self.ids)
        waiter = Future()
        with self.lock:
            if self.process.poll() is not None or self.process.stdin.closed:
                raise RuntimeError("星邮运行端已停止")
            self.waiters[request_id] = waiter
            try:
                self.process.stdin.write(json.dumps({"id": request_id, "op": op, "args": args or {}}) + "\n")
                self.process.stdin.flush()
            except OSError:
                self.waiters.pop(request_id, None)
                raise
        return await asyncio.wait_for(asyncio.shield(asyncio.wrap_future(waiter)), timeout=95)

    def close(self):
        with self.lock:
            self.process.stdin.close()
        try:
            self.process.wait(timeout=4)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
        self.reader.join(timeout=2)
        self.process.stdout.close()

