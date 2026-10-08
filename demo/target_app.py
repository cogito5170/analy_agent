"""Mini Shop — a small HTTP service used as the system under test.

It intentionally contains defects so the pipeline has something real to find.
The seeded defects are listed in demo/SEEDED_DEFECTS.md; the agents never read
that file — it is only there so a human can check what the pipeline caught.
"""

from __future__ import annotations

import json
import re
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

USERS = {
    "alice@example.com": "Correct#Pass1",
    "locktest@example.com": "Correct#Pass1",
}
PRODUCTS = ["red shoes", "blue shoes", "red hat", "green bag", "black bag"]
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class State:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.cold_start = True
        self.reset()

    def reset(self) -> None:
        self.failures: dict[str, int] = {}
        self.locked: set[str] = set()
        self.tokens: dict[str, str] = {}
        self.payments: list[dict] = []
        self.idempotency: dict[str, str] = {}


class Handler(BaseHTTPRequestHandler):
    state: State
    server_version = "MiniShop/0.1"

    def log_message(self, *args) -> None:
        pass

    def _send(self, status: int, body: dict) -> None:
        raw = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        try:
            data = json.loads(self.rfile.read(length))
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}

    def _user(self) -> str | None:
        auth = self.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return None
        return self.state.tokens.get(auth[7:])

    def do_GET(self) -> None:
        url = urlparse(self.path)
        if url.path == "/health":
            return self._send(200, {"status": "ok"})
        if url.path == "/api/products":
            return self._search(parse_qs(url.query))
        if url.path == "/api/me":
            user = self._user()
            if user is None:
                return self._send(401, {"error": "unauthorized"})
            return self._send(200, {"email": user})
        self._send(404, {"error": "not found"})

    def do_POST(self) -> None:
        url = urlparse(self.path)
        if url.path == "/__reset":
            with self.state.lock:
                self.state.reset()
            return self._send(200, {"reset": True})
        if url.path == "/api/login":
            return self._login(self._body())
        if url.path == "/api/payments":
            return self._pay(self._body())
        self._send(404, {"error": "not found"})

    def _login(self, data: dict) -> None:
        email, password = data.get("email"), data.get("password")
        if not isinstance(email, str) or not EMAIL_RE.match(email):
            return self._send(400, {"error": "invalid email"})
        # Seeded defect: the upper bound check is off by one (> 65 instead of > 64).
        if not isinstance(password, str) or len(password) < 8 or len(password) > 65:
            return self._send(400, {"error": "invalid password"})
        with self.state.lock:
            if email in self.state.locked:
                return self._send(423, {"error": "account locked"})
            if email not in USERS:
                return self._send(401, {"error": "invalid credentials"})
            if USERS[email] != password:
                count = self.state.failures.get(email, 0) + 1
                self.state.failures[email] = count
                if count >= 5:
                    self.state.locked.add(email)
                # Seeded defect: the wrong-password branch crashes instead of returning 401.
                return self._send(500, {"error": "Internal Server Error",
                                        "trace": "KeyError: 'last_login'"})
            self.state.failures[email] = 0
            token = uuid.uuid4().hex
            self.state.tokens[token] = email
        self._send(200, {"token": token, "redirect": "/dashboard"})

    def _pay(self, data: dict) -> None:
        user = self._user()
        if user is None:
            return self._send(401, {"error": "unauthorized"})
        amount = data.get("amount")
        # Seeded defect: the lower bound accepts 0 (>= 0 instead of >= 1).
        if not isinstance(amount, int) or isinstance(amount, bool) or amount < 0 or amount > 1_000_000:
            return self._send(400, {"error": "invalid amount"})
        key = self.headers.get("Idempotency-Key")
        with self.state.lock:
            # Seeded defect: the idempotency key is stored but never consulted,
            # so a retried request charges the customer twice.
            payment_id = uuid.uuid4().hex[:12]
            if key:
                self.state.idempotency[key] = payment_id
            self.state.payments.append({"id": payment_id, "user": user, "amount": amount})
        self._send(200, {"payment_id": payment_id, "amount": amount})

    def _search(self, query: dict) -> None:
        q = (query.get("q") or [""])[0]
        if not q or len(q) > 50:
            return self._send(400, {"error": "invalid query"})
        with self.state.lock:
            cold = self.state.cold_start
            self.state.cold_start = False
        if cold:
            # Seeded environment issue: the first request after boot hits a cold cache.
            return self._send(503, {"error": "warming up"})
        # Searching is slower than the (unstated) target the spec calls "fast".
        time.sleep(0.6)
        self._send(200, {"results": [p for p in PRODUCTS if q.lower() in p]})


def start(port: int = 0) -> tuple[ThreadingHTTPServer, str]:
    """Start the app in a background thread; return the server and its base URL."""
    handler = type("BoundHandler", (Handler,), {"state": State()})
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


if __name__ == "__main__":
    import sys

    srv, url = start(int(sys.argv[1]) if len(sys.argv) > 1 else 8765)
    print(f"Mini Shop listening on {url}")
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        srv.shutdown()
