from __future__ import annotations

import json
import queue
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

import bpy

from .bake_runtime import execute_external_parent_bake
from .http_utils import bind_threading_http_server
from .protocol import parse_bake_request
from .scene_query import collect_scene_summary
from .ui_service import (
    UIServiceRuntime,
    browser_host_for_url,
    has_web_bundle,
    resolve_web_bundle_dir,
    start_ui_service,
    stop_ui_service,
)

DEFAULT_PREFERRED_API_PORT = 37601


@dataclass(slots=True)
class PendingRequest:
    method: str
    path: str
    payload: dict[str, Any] | None
    response_queue: queue.Queue[tuple[int, dict[str, Any]]]


@dataclass(slots=True)
class ServiceRuntime:
    host: str
    port: int
    request_queue: queue.Queue[PendingRequest] = field(default_factory=queue.Queue)
    server: ThreadingHTTPServer | None = None
    thread: threading.Thread | None = None
    timer_registered: bool = False
    ui_runtime: UIServiceRuntime | None = None
    ui_bundle_available: bool = False
    ui_error: str | None = None


_runtime: ServiceRuntime | None = None


def start_service(host: str, preferred_port: int = DEFAULT_PREFERRED_API_PORT) -> None:
    global _runtime

    if _runtime is not None:
        if _runtime.host == host:
            if _runtime.ui_runtime is None and has_web_bundle(resolve_web_bundle_dir()):
                _runtime.ui_runtime = start_ui_service(
                    host=host,
                    api_base_url=_build_api_base_url(_runtime.host, _runtime.port),
                    bundle_dir=resolve_web_bundle_dir(),
                )
                _runtime.ui_bundle_available = _runtime.ui_runtime is not None
                _runtime.ui_error = None if _runtime.ui_runtime is not None else "Web UI bundle missing"
            return
        stop_service()

    runtime = ServiceRuntime(host=host, port=0)
    bundle_dir = resolve_web_bundle_dir()
    runtime.ui_bundle_available = has_web_bundle(bundle_dir)

    try:
        runtime.server = bind_threading_http_server(host, preferred_port, _build_handler(runtime))
        runtime.port = runtime.server.server_port
        runtime.thread = threading.Thread(
            target=runtime.server.serve_forever,
            name="mmd-ext-parent-baker-http",
            daemon=True,
        )
        runtime.thread.start()
        bpy.app.timers.register(_process_pending_requests, first_interval=0.1, persistent=True)
        runtime.timer_registered = True

        if runtime.ui_bundle_available:
            runtime.ui_runtime = start_ui_service(
                host=host,
                api_base_url=_build_api_base_url(runtime.host, runtime.port),
                bundle_dir=bundle_dir,
            )
            runtime.ui_error = None if runtime.ui_runtime is not None else "Web UI bundle missing"
        else:
            runtime.ui_error = "Web UI bundle missing"
    except Exception:
        stop_ui_service(runtime.ui_runtime)
        if runtime.server is not None:
            runtime.server.shutdown()
            runtime.server.server_close()
        if runtime.thread is not None:
            runtime.thread.join(timeout=1.0)
        if runtime.timer_registered:
            try:
                bpy.app.timers.unregister(_process_pending_requests)
            except Exception:
                pass
        raise

    _runtime = runtime


def stop_service() -> None:
    global _runtime

    runtime = _runtime
    _runtime = None
    if runtime is None:
        return

    stop_ui_service(runtime.ui_runtime)
    if runtime.server is not None:
        runtime.server.shutdown()
        runtime.server.server_close()
    if runtime.thread is not None:
        runtime.thread.join(timeout=1.0)
    if runtime.timer_registered:
        try:
            bpy.app.timers.unregister(_process_pending_requests)
        except Exception:
            pass


def get_service_status() -> dict[str, Any]:
    runtime = _runtime
    ui_bundle_available = has_web_bundle(resolve_web_bundle_dir())
    if runtime is None:
        return {
            "running": False,
            "host": None,
            "port": None,
            "base_url": None,
            "api_running": False,
            "api_base_url": None,
            "ui_running": False,
            "ui_port": None,
            "ui_base_url": None,
            "ui_launch_url": None,
            "ui_bundle_available": ui_bundle_available,
            "ui_error": None if ui_bundle_available else "Web UI bundle missing",
        }
    api_base_url = _build_api_base_url(runtime.host, runtime.port)
    return {
        "running": True,
        "host": runtime.host,
        "port": runtime.port,
        "base_url": api_base_url,
        "api_running": True,
        "api_base_url": api_base_url,
        "ui_running": runtime.ui_runtime is not None,
        "ui_port": runtime.ui_runtime.port if runtime.ui_runtime is not None else None,
        "ui_base_url": runtime.ui_runtime.base_url if runtime.ui_runtime is not None else None,
        "ui_launch_url": runtime.ui_runtime.launch_url if runtime.ui_runtime is not None else None,
        "ui_bundle_available": runtime.ui_bundle_available,
        "ui_error": None if runtime.ui_runtime is not None else runtime.ui_error,
    }


def _build_api_base_url(host: str, port: int) -> str:
    return f"http://{browser_host_for_url(host)}:{port}"


def _process_pending_requests() -> float | None:
    runtime = _runtime
    if runtime is None:
        return None

    while True:
        try:
            pending_request = runtime.request_queue.get_nowait()
        except queue.Empty:
            break

        try:
            status_code, payload = _dispatch_request(
                method=pending_request.method,
                path=pending_request.path,
                payload=pending_request.payload,
            )
        except ValueError as exc:
            status_code, payload = 400, {"error": str(exc)}
        except Exception as exc:
            status_code, payload = 500, {"error": str(exc)}
        pending_request.response_queue.put((status_code, payload))

    return 0.1


def _dispatch_request(method: str, path: str, payload: dict[str, Any] | None) -> tuple[int, dict[str, Any]]:
    if method == "GET" and path == "/scene":
        return 200, collect_scene_summary().to_payload()

    if method == "POST" and path == "/bake/external-parent":
        if payload is None:
            raise ValueError("request body must be a JSON object")
        request = parse_bake_request(payload)
        return 200, execute_external_parent_bake(request)

    return 404, {"error": f'unsupported endpoint: {method} {path}'}


def _build_handler(runtime: ServiceRuntime):
    class RequestHandler(BaseHTTPRequestHandler):
        server_version = "MMDExtParentBaker/0.1"

        def do_OPTIONS(self) -> None:
            self.send_response(204)
            self._write_common_headers()
            self.end_headers()

        def do_GET(self) -> None:
            self._handle_request("GET")

        def do_POST(self) -> None:
            self._handle_request("POST")

        def log_message(self, format: str, *args: object) -> None:
            _ = format, args

        def _handle_request(self, method: str) -> None:
            path = urlparse(self.path).path
            payload = None
            if method == "POST":
                payload = self._read_json_payload()
                if payload is None:
                    return

            response_queue: queue.Queue[tuple[int, dict[str, Any]]] = queue.Queue(maxsize=1)
            runtime.request_queue.put(
                PendingRequest(
                    method=method,
                    path=path,
                    payload=payload,
                    response_queue=response_queue,
                )
            )

            try:
                status_code, response_payload = response_queue.get(timeout=300.0)
            except queue.Empty:
                status_code, response_payload = 504, {"error": "Blender main thread did not answer in time"}

            self.send_response(status_code)
            self._write_common_headers()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(response_payload, ensure_ascii=False).encode("utf-8"))

        def _read_json_payload(self) -> dict[str, Any] | None:
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length) if content_length > 0 else b"{}"
            try:
                payload = json.loads(raw_body.decode("utf-8"))
            except json.JSONDecodeError:
                self.send_response(400)
                self._write_common_headers()
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "request body must be valid JSON"}).encode("utf-8"))
                return None
            if not isinstance(payload, dict):
                self.send_response(400)
                self._write_common_headers()
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "request body must be a JSON object"}).encode("utf-8"))
                return None
            return payload

        def _write_common_headers(self) -> None:
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

    return RequestHandler
