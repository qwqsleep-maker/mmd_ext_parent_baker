from __future__ import annotations

import json
import mimetypes
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from .http_utils import build_ui_launch_url, bind_threading_http_server


def browser_host_for_url(bind_host: str) -> str:
    if bind_host in {"0.0.0.0", "::"}:
        return "127.0.0.1"
    return bind_host


def resolve_web_bundle_dir() -> Path:
    return Path(__file__).resolve().parent / "web_dist"


def has_web_bundle(bundle_dir: Path | None = None) -> bool:
    root = bundle_dir or resolve_web_bundle_dir()
    return (root / "index.html").is_file()


@dataclass(slots=True)
class UIServiceRuntime:
    bind_host: str
    browser_host: str
    port: int
    api_base_url: str
    bundle_dir: Path
    server: ThreadingHTTPServer | None = None
    thread: threading.Thread | None = None

    @property
    def base_url(self) -> str:
        return f"http://{self.browser_host}:{self.port}"

    @property
    def launch_url(self) -> str:
        return build_ui_launch_url(self.base_url, self.api_base_url)


def start_ui_service(host: str, api_base_url: str, bundle_dir: Path | None = None) -> UIServiceRuntime | None:
    root = (bundle_dir or resolve_web_bundle_dir()).resolve()
    if not has_web_bundle(root):
        return None

    runtime = UIServiceRuntime(
        bind_host=host,
        browser_host=browser_host_for_url(host),
        port=0,
        api_base_url=api_base_url,
        bundle_dir=root,
    )
    runtime.server = bind_threading_http_server(host, 0, _build_handler(runtime))
    runtime.port = runtime.server.server_port
    runtime.thread = threading.Thread(
        target=runtime.server.serve_forever,
        name="mmd-ext-parent-baker-ui-http",
        daemon=True,
    )
    runtime.thread.start()
    return runtime


def stop_ui_service(runtime: UIServiceRuntime | None) -> None:
    if runtime is None:
        return
    if runtime.server is not None:
        runtime.server.shutdown()
        runtime.server.server_close()
    if runtime.thread is not None:
        runtime.thread.join(timeout=1.0)


def _build_handler(runtime: UIServiceRuntime):
    class RequestHandler(BaseHTTPRequestHandler):
        server_version = "MMDExtParentBakerUI/0.1"

        def do_GET(self) -> None:
            path = urlparse(self.path).path
            if path == "/__mmd_ext_parent_config.json":
                payload = json.dumps(
                    {
                        "apiBaseUrl": runtime.api_base_url,
                        "uiBaseUrl": runtime.base_url,
                    },
                    ensure_ascii=False,
                ).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(payload)
                return

            file_path = _resolve_bundle_file(runtime.bundle_dir, path)
            if file_path is None:
                self.send_response(404)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.end_headers()
                self.wfile.write(b"not found")
                return

            content_type, _encoding = mimetypes.guess_type(str(file_path))
            self.send_response(200)
            self.send_header("Content-Type", content_type or "application/octet-stream")
            self.end_headers()
            self.wfile.write(file_path.read_bytes())

        def log_message(self, format: str, *args: Any) -> None:
            _ = format, args

    return RequestHandler


def _resolve_bundle_file(bundle_dir: Path, request_path: str) -> Path | None:
    if request_path in {"", "/"}:
        candidate = bundle_dir / "index.html"
    else:
        relative_path = unquote(request_path).lstrip("/")
        candidate = (bundle_dir / relative_path).resolve()
    try:
        candidate.relative_to(bundle_dir)
    except ValueError:
        return None
    if not candidate.is_file():
        return None
    return candidate
