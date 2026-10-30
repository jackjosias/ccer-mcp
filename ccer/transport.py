"""Bounded MCP stdio transport: no shell, correlated IDs, no silent retry."""
import json
import queue
import subprocess
import threading
import time
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


class DeferredConcatTransport:
    """Keep the direct MCP online while its optional Concat backend is offline.

    Only a fresh caller request may reconnect. A request that failed after
    dispatch is NEVER replayed automatically.
    """

    def __init__(self, binary, mode="window", retry_seconds=5, *, permit_launch=True):
        if type(permit_launch) is not bool:
            raise ValueError("permit_launch must be boolean")
        self.permit_launch = permit_launch
        self.binary = Path(binary)
        self.mode = mode
        self.retry_seconds = retry_seconds
        self._link = None
        self._retry_at = 0.0
        self._lock = threading.RLock()

    def _discard(self):
        previous, self._link = self._link, None
        if previous is not None:
            previous.close()

    def _ensure(self):
        if not self.permit_launch:
            raise TransportError(
                "CCER single-window GUI-FIRST: spawning a second Concat process is disabled")
        if self._link is not None:
            process = self._link.process
            if process is not None and process.poll() is None:
                return self._link
            self._discard()
        if time.monotonic() < self._retry_at:
            raise TransportError("Concat backend offline; safe reconnect is rate-limited")
        fresh = ConcatTransport(self.binary, self.mode)
        try:
            fresh.start()
        except (TransportError, OSError, ValueError) as error:
            fresh.close()
            self._retry_at = time.monotonic() + self.retry_seconds
            raise TransportError(f"Concat backend unavailable: {error}") from error
        self._retry_at = 0.0
        self._link = fresh
        return fresh

    def start(self):
        # Prewarm only; Concat need not already be running at user login.
        self.tools()

    def tools(self):
        with self._lock:
            try:
                return self._ensure().tools()
            except (TransportError, OSError):
                self._discard()
                return []

    def tool(self, name, arguments=None, timeout=None):
        with self._lock:
            link = self._ensure()
            try:
                return link.tool(name, arguments, timeout)
            except (TransportError, OSError):
                self._discard()
                raise

    def close(self):
        with self._lock:
            self._discard()


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
