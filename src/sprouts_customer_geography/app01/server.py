"""Loopback-only, read-only APP-01 HTTP runtime."""

from __future__ import annotations

import argparse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import sys
from typing import Sequence
from urllib.parse import urlsplit
import webbrowser

from .bundle import BundleSet, build_bundle_set
from .errors import App01Error


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8767
CSP = (
    "default-src 'none'; "
    "script-src 'self'; "
    "style-src 'self'; "
    "img-src 'self' data: blob: https://basemap.nationalmap.gov; "
    "connect-src 'self' https://basemap.nationalmap.gov; "
    "worker-src 'self' blob:; "
    "font-src 'self'; "
    "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'"
)


def _static_routes(repository_root: Path) -> dict[str, Path]:
    site = repository_root / "presentation" / "app01" / "site"
    vendor = repository_root / "presentation" / "arch01" / "site" / "vendor" / "maplibre-gl"
    return {
        "/": site / "index.html",
        "/index.html": site / "index.html",
        "/app.mjs": site / "app.mjs",
        "/styles.css": site / "styles.css",
        "/vendor/maplibre-gl/maplibre-gl.mjs": vendor / "maplibre-gl.mjs",
        "/vendor/maplibre-gl/maplibre-gl-shared.mjs": vendor / "maplibre-gl-shared.mjs",
        "/vendor/maplibre-gl/maplibre-gl-worker.mjs": vendor / "maplibre-gl-worker.mjs",
        "/vendor/maplibre-gl/maplibre-gl.css": vendor / "maplibre-gl.css",
        "/vendor/maplibre-gl/LICENSE.txt": vendor / "LICENSE.txt",
        "/config/runtime.json": repository_root / "config" / "app01" / "app01_runtime_policy.json",
    }


class App01Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, address: tuple[str, int], bundles: BundleSet, repository_root: Path):
        super().__init__(address, App01RequestHandler)
        self.bundles = bundles
        self.static_routes = _static_routes(repository_root)
        host, port = self.server_address
        self.allowed_hosts = {f"{host}:{port}", f"localhost:{port}"}


class App01RequestHandler(BaseHTTPRequestHandler):
    server: App01Server
    protocol_version = "HTTP/1.1"
    server_version = "APP01"
    sys_version = ""

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def version_string(self) -> str:
        return self.server_version

    def _base_headers(self, content_type: str, content_length: int, cache_control: str = "no-store") -> None:
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(content_length))
        self.send_header("Cache-Control", cache_control)
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Permissions-Policy", "geolocation=(), camera=(), microphone=(), payment=(), usb=(), interest-cohort=()")

    def _send(self, status: HTTPStatus, payload: bytes, content_type: str, cache_control: str = "no-store") -> None:
        self.send_response(status)
        self._base_headers(content_type, len(payload), cache_control)
        self.end_headers()
        self.wfile.write(payload)

    def _invalid_host(self) -> bool:
        host = self.headers.get("Host", "").lower()
        if host not in self.server.allowed_hosts:
            self._send(HTTPStatus.FORBIDDEN, b'{"error":"loopback_host_required"}\n', "application/json; charset=utf-8")
            return True
        return False

    def do_GET(self) -> None:  # noqa: N802 - standard-library handler contract
        if self._invalid_host():
            return
        parsed = urlsplit(self.path)
        if parsed.query or parsed.fragment:
            self._send(HTTPStatus.BAD_REQUEST, b'{"error":"query_strings_not_supported"}\n', "application/json; charset=utf-8")
            return
        path = parsed.path
        if path == "/health":
            payload = json.dumps(self.server.bundles.health, sort_keys=True).encode("utf-8") + b"\n"
            self._send(HTTPStatus.OK, payload, "application/json; charset=utf-8")
            return
        if path == "/data/presentation.json":
            self._send(HTTPStatus.OK, self.server.bundles.presentation_bytes, "application/json; charset=utf-8")
            return
        if path == "/data/evidence.json":
            self._send(HTTPStatus.OK, self.server.bundles.evidence_bytes, "application/json; charset=utf-8")
            return
        if path == "/data/geometry.geojson":
            self._send(HTTPStatus.OK, self.server.bundles.geometry_bytes, "application/geo+json; charset=utf-8")
            return
        if path == "/favicon.ico":
            self._send(HTTPStatus.NO_CONTENT, b"", "image/x-icon")
            return
        file_path = self.server.static_routes.get(path)
        if file_path is None or not file_path.is_file():
            self._send(HTTPStatus.NOT_FOUND, b'{"error":"not_found"}\n', "application/json; charset=utf-8")
            return
        content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        if file_path.suffix in {".mjs", ".js"}:
            content_type = "text/javascript; charset=utf-8"
        elif file_path.suffix == ".json":
            content_type = "application/json; charset=utf-8"
        elif file_path.suffix in {".html", ".css", ".txt"}:
            content_type = f"{content_type}; charset=utf-8"
        cache_control = "public, max-age=31536000, immutable" if "/vendor/" in path else "no-store"
        self._send(HTTPStatus.OK, file_path.read_bytes(), content_type, cache_control)

    def _method_not_allowed(self) -> None:
        if self._invalid_host():
            return
        self._send(HTTPStatus.METHOD_NOT_ALLOWED, b'{"error":"get_only_runtime"}\n', "application/json; charset=utf-8")

    do_HEAD = _method_not_allowed
    do_POST = _method_not_allowed
    do_PUT = _method_not_allowed
    do_PATCH = _method_not_allowed
    do_DELETE = _method_not_allowed
    do_OPTIONS = _method_not_allowed


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Launch the APP-01 local Michigan customer-geography dashboard")
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--settings", type=Path)
    parser.add_argument("--synthetic", action="store_true", help="Use deterministic synthetic validation data instead of accepted real inputs")
    parser.add_argument("--check", action="store_true", help="Validate and construct the selected runtime in memory, then exit")
    parser.add_argument("--open", action="store_true", dest="open_browser", help="Open the default browser after readiness")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if not 1024 <= args.port <= 65535:
        print("APP01_PORT_INVALID: Choose a local port between 1024 and 65535.", file=sys.stderr)
        return 2
    root = args.repository_root.resolve()
    settings = None if args.settings is None else args.settings.resolve()
    try:
        bundles = build_bundle_set(root, synthetic=args.synthetic, settings_path=settings)
    except App01Error as exc:
        print(f"APP-01 could not start ({exc.code}). {exc.operator_message}", file=sys.stderr)
        return 2
    if args.check:
        print(json.dumps(dict(bundles.health), sort_keys=True))
        return 0
    try:
        server = App01Server((DEFAULT_HOST, args.port), bundles, root)
    except OSError:
        print(f"APP-01 could not start (APP01_PORT_OCCUPIED). Local port {args.port} is already in use.", file=sys.stderr)
        return 2
    url = f"http://{DEFAULT_HOST}:{args.port}/"
    print(f"APP-01 is ready at {url}", flush=True)
    print("Press Ctrl+C to stop the local application.", flush=True)
    if args.open_browser:
        try:
            webbrowser.open(url, new=2, autoraise=True)
        except webbrowser.Error:
            print("The browser did not open automatically. Open the local address shown above.", flush=True)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
