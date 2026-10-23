"""Bounded MCP stdio transport: no shell, correlated IDs, no silent retry."""
import json
import queue
import subprocess
import threading
from pathlib import Path


class TransportError(RuntimeError):
    pass


class ConcatTransport:
    def __init__(self, binary: Path, mode="window", timeout=30):
        self.binary = Path(binary).expanduser().resolve()
        if mode not in ("window", "headless"):
            raise ValueError("Use window or headless mode explicitly")
        self.mode, self.timeout = mode, timeout
        self.process = None
        self.lock = threading.RLock()
        self.pending = {}
        self.counter = 0

    def start(self):
        if not self.binary.is_file():
            raise TransportError("Concat binary missing: " + str(self.binary))
        self.process = subprocess.Popen(
            [str(self.binary), "--mcp", self.mode],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, encoding="utf-8", bufsize=1)
        threading.Thread(target=self._read, daemon=True).start()
        welcome = self.call("initialize", {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "ccer", "version": "0.1.0"},
        })
        if not welcome.get("serverInfo"):
            raise TransportError("Invalid Concat handshake")
        self.notify("notifications/initialized")

    def _read(self):
        try:
            for line in self.process.stdout:
                try:
                    msg = json.loads(line)
                except ValueError:
                    continue
                ident = msg.get("id")
                with self.lock:
                    channel = self.pending.get(ident) if isinstance(ident, int) else None
                if channel:
                    channel.put(msg)
        finally:
            with self.lock:
                for channel in self.pending.values():
                    channel.put({"error": {"message": "Concat disconnected"}})

    def notify(self, method, params=None):
        message = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            message["params"] = params
        with self.lock:
            if not self.process or not self.process.stdin:
                raise TransportError("Concat unavailable")
            self.process.stdin.write(json.dumps(message) + "\n")
            self.process.stdin.flush()

    def call(self, method, params=None, timeout=None):
        with self.lock:
            if not self.process or self.process.poll() is not None:
                raise TransportError("Concat subprocess stopped")
            self.counter += 1
            ident = self.counter
            channel = queue.Queue(maxsize=2)
            self.pending[ident] = channel
            try:
                self.process.stdin.write(json.dumps({
                    "jsonrpc": "2.0", "id": ident, "method": method,
                    "params": params or {},
                }, ensure_ascii=False) + "\n")
                self.process.stdin.flush()
            except OSError as exc:
                self.pending.pop(ident, None)
                raise TransportError("Cannot write to Concat") from exc
        try:
            msg = channel.get(timeout=timeout or self.timeout)
        except queue.Empty as exc:
            try:
                self.notify("notifications/cancelled", {"requestId": ident})
            except TransportError:
                pass
            raise TransportError(f"Timeout {method}; operation outcome UNKNOWN") from exc
        finally:
            with self.lock:
                self.pending.pop(ident, None)
        if "error" in msg:
            raise TransportError(str(msg["error"]))
        return msg.get("result", {})

    def tool(self, name, arguments=None, timeout=None):
        result = self.call("tools/call", {
            "name": name, "arguments": arguments or {}}, timeout)
        if result.get("isError"):
            raise TransportError(str(result.get("structuredContent", result.get("content"))))
        return result

    def tools(self):
        return self.call("tools/list").get("tools", [])

    def close(self):
        if self.process:
            p = self.process
            try:
                p.stdin.close()
                p.wait(timeout=3)
            except (OSError, subprocess.TimeoutExpired):
                p.terminate()
                try:
                    p.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    p.kill()
                    p.wait()
            self.process = None


def structured(result):
    if isinstance(result.get("structuredContent"), dict):
        return result["structuredContent"]
    for item in result.get("content", []):
        if item.get("type") == "text":
            try:
                parsed = json.loads(item["text"])
                if isinstance(parsed, dict):
                    return parsed
            except (KeyError, ValueError):
                pass
    return result
