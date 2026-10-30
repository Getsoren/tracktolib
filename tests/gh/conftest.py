from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from typing import cast

import pytest


@dataclass
class FakeRequest:
    method: str
    path: str
    headers: dict[str, str]
    body: str


@dataclass
class FakeGitHub:
    """Replies with a canned response and records what the client sent."""

    url: str = ""
    status: int = 200
    body: str = "{}"
    content_type: str = "application/json"
    requests: list[FakeRequest] = field(default_factory=list)
    # (status, body) per path without the query, overriding the canned response
    routes: dict[str, tuple[int, str]] = field(default_factory=dict)


class FakeGitHubServer(HTTPServer):
    fake: FakeGitHub


class FakeGitHubHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Overridden to prevent logging
        pass

    def _serve(self):
        fake = cast("FakeGitHubServer", self.server).fake
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length).decode() if length else ""
        fake.requests.append(FakeRequest(self.command, self.path, dict(self.headers), body))

        status, body = fake.routes.get(self.path.split("?")[0], (fake.status, fake.body))
        payload = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", fake.content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    do_GET = _serve
    do_POST = _serve


@pytest.fixture
def fake_github():
    server = FakeGitHubServer(("localhost", 0), FakeGitHubHandler)
    server.fake = FakeGitHub(url="http://{}:{}".format(*server.server_address))

    thread = Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()

    yield server.fake

    server.shutdown()
    server.server_close()
