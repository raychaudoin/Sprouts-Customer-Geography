"""Serve the ARCH-01 architecture spike over a loopback-only allowlist."""

from __future__ import annotations

import argparse
import json
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

try:
    from .build_synthetic_bundle import (
        METRIC_CATALOG_PATH,
        REPOSITORY,
        build_bundle_bytes,
        load_accepted_geometry_bytes,
    )
except ImportError:  # Direct-script execution.
    from build_synthetic_bundle import (
        METRIC_CATALOG_PATH,
        REPOSITORY,
        build_bundle_bytes,
        load_accepted_geometry_bytes,
    )


SITE_ROOT = REPOSITORY / "presentation" / "arch01" / "site"
RUNTIME_POLICY_PATH = REPOSITORY / "config" / "arch01" / "arch01_runtime_policy.json"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8766
CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self'; "
    "img-src 'self' data: blob: https://basemap.nationalmap.gov; "
    "connect-src 'self' https://basemap.nationalmap.gov; "
    "worker-src 'self' blob:; "
    "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'"
)


def _static_routes() -> dict[str, Path]:
    return {
        "/": SITE_ROOT / "index.html",
        "/index.html": SITE_ROOT / "index.html",
        "/app.mjs": SITE_ROOT / "app.mjs",
        "/styles.css": SITE_ROOT / "styles.css",
        "/vendor/maplibre-gl/maplibre-gl.mjs": SITE_ROOT / "vendor" / "maplibre-gl" / "maplibre-gl.mjs",
        "/vendor/maplibre-gl/maplibre-gl-shared.mjs": SITE_ROOT / "vendor" / "maplibre-gl" / "maplibre-gl-shared.mjs",
        "/vendor/maplibre-gl/maplibre-gl-worker.mjs": SITE_ROOT / "vendor" / "maplibre-gl" / "maplibre-gl-worker.mjs",
        "/vendor/maplibre-gl/maplibre-gl.css": SITE_ROOT / "vendor" / "maplibre-gl" / "maplibre-gl.css",
        "/vendor/maplibre-gl/LICENSE.txt": SITE_ROOT / "vendor" / "maplibre-gl" / "LICENSE.txt",
        "/config/metrics.json": METRIC_CATALOG_PATH,
        "/config/runtime.json": RUNTIME_POLICY_PATH,
    }


class Arch01Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], bundle_bytes: bytes, geometry_bytes: bytes):
        super().__init__(address, Arch01RequestHandler)
        self.bundle_bytes = bundle_bytes
        self.geometry_bytes = geometry_bytes
        host, port = self.server_address
        self.allowed_hosts = {f"{host}:{port}", f"localhost:{port}"}


class Arch01RequestHandler(BaseHTTPRequestHandler):
    server: Arch01Server
    protocol_version = "HTTP/1.1"

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def _base_headers(self, content_type: str, content_length: int, cache_control: str = "no-store") -> None:
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(content_length))
        self.send_header("Cache-Control", cache_control)
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Permissions-Policy", "geolocation=(), camera=(), microphone=(), payment=(), usb=()")

    def _send(self, status: HTTPStatus, payload: bytes, content_type: str, cache_control: str = "no-store") -> None:
        self.send_response(status)
        self._base_headers(content_type, len(payload), cache_control)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(payload)

    def _reject_invalid_host(self) -> bool:
        host = self.headers.get("Host", "").lower()
        if host not in self.server.allowed_hosts:
            self._send(HTTPStatus.FORBIDDEN, b'{"error":"loopback_host_required"}\n', "application/json; charset=utf-8")
            return True
        return False

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler contract
        if self._reject_invalid_host():
            return
        parsed = urlsplit(self.path)
        if parsed.query or parsed.fragment:
            self._send(HTTPStatus.BAD_REQUEST, b'{"error":"query_strings_not_supported"}\n', "application/json; charset=utf-8")
            return
        path = parsed.path
        if path == "/health":
            payload = json.dumps(
                {"state": "ready", "binding": "loopback", "data_mode": "synthetic_architecture_evidence", "tract_count": 3017},
                sort_keys=True,
            ).encode("utf-8") + b"\n"
            self._send(HTTPStatus.OK, payload, "application/json; charset=utf-8")
            return
        if path == "/data/presentation.json":
            self._send(HTTPStatus.OK, self.server.bundle_bytes, "application/json; charset=utf-8")
            return
        if path == "/data/geometry.geojson":
            self._send(HTTPStatus.OK, self.server.geometry_bytes, "application/json; charset=utf-8")
            return
        if path == "/favicon.ico":
            self._send(HTTPStatus.NO_CONTENT, b"", "image/x-icon")
            return
        file_path = _static_routes().get(path)
        if file_path is None or not file_path.is_file():
            self._send(HTTPStatus.NOT_FOUND, b'{"error":"not_found"}\n', "application/json; charset=utf-8")
            return
        content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        if file_path.suffix in {".mjs", ".js"}:
            content_type = "text/javascript; charset=utf-8"
        elif file_path.suffix in {".json", ".geojson"}:
            content_type = "application/json; charset=utf-8"
        elif file_path.suffix in {".html", ".css", ".txt"}:
            content_type = f"{content_type}; charset=utf-8"
        cache_control = "public, max-age=31536000, immutable" if "/vendor/" in path else "no-store"
        self._send(HTTPStatus.OK, file_path.read_bytes(), content_type, cache_control)

    def do_HEAD(self) -> None:  # noqa: N802 - stdlib handler contract
        self.do_GET()

    def _method_not_allowed(self) -> None:
        if self._reject_invalid_host():
            return
        self._send(HTTPStatus.METHOD_NOT_ALLOWED, b'{"error":"read_only_runtime"}\n', "application/json; charset=utf-8")

    do_POST = _method_not_allowed
    do_PUT = _method_not_allowed
    do_PATCH = _method_not_allowed
    do_DELETE = _method_not_allowed
    do_OPTIONS = _method_not_allowed


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve the local-only ARCH-01 architecture spike.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--check", action="store_true", help="Build and validate the synthetic bundle, then exit.")
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        raise SystemExit("ARCH01_PORT_INVALID: port must be between 1024 and 65535")
    bundle_bytes = build_bundle_bytes()
    geometry_bytes = load_accepted_geometry_bytes()
    if args.check:
        print(json.dumps({"state": "ready", "binding": DEFAULT_HOST, "bundle_bytes": len(bundle_bytes)}, sort_keys=True))
        return 0
    server = Arch01Server((DEFAULT_HOST, args.port), bundle_bytes, geometry_bytes)
    print(f"ARCH-01 spike ready at http://{DEFAULT_HOST}:{args.port}/", flush=True)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
