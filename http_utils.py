from __future__ import annotations

import errno
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


WINDOWS_ADDRESS_IN_USE = 10048
WINDOWS_ACCESS_DENIED_ON_BIND = 10013


class ExclusiveThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = False

    def server_bind(self) -> None:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def bind_threading_http_server(
    host: str,
    preferred_port: int,
    handler: type[BaseHTTPRequestHandler],
) -> ThreadingHTTPServer:
    if int(preferred_port) == 0:
        server = ExclusiveThreadingHTTPServer((host, 0), handler)
        server.daemon_threads = True
        return server

    start_port = max(1, int(preferred_port))
    last_error: OSError | None = None

    for candidate_port in range(start_port, 65536):
        try:
            server = ExclusiveThreadingHTTPServer((host, candidate_port), handler)
        except OSError as exc:
            if _is_address_in_use_error(exc):
                last_error = exc
                continue
            raise

        server.daemon_threads = True
        return server

    raise OSError(
        errno.EADDRINUSE,
        f"no available port found from {start_port} to 65535 for host {host}",
    ) from last_error


def build_ui_launch_url(ui_base_url: str, api_base_url: str) -> str:
    parts = urlsplit(ui_base_url)
    query_items = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True) if key != "apiBaseUrl"]
    query_items.append(("apiBaseUrl", api_base_url))
    path = parts.path or "/"
    return urlunsplit((parts.scheme, parts.netloc, path, urlencode(query_items), parts.fragment))


def _is_address_in_use_error(error: OSError) -> bool:
    return (
        error.errno == errno.EADDRINUSE
        or getattr(error, "winerror", None) == WINDOWS_ADDRESS_IN_USE
        or getattr(error, "winerror", None) == WINDOWS_ACCESS_DENIED_ON_BIND
    )
