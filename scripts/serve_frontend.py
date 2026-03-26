from __future__ import annotations

import argparse
import http.server
import socketserver
from pathlib import Path
from urllib.parse import unquote, urlsplit


class ThreadingHttpServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


class SpaStaticHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, directory: str, **kwargs):
        self._root = Path(directory)
        super().__init__(*args, directory=directory, **kwargs)

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self) -> None:
        self._serve(send_body=True)

    def do_HEAD(self) -> None:
        self._serve(send_body=False)

    def _serve(self, send_body: bool) -> None:
        parsed = urlsplit(self.path)
        request_path = unquote(parsed.path or "/")

        if request_path.startswith("/api/"):
            self.send_error(404, "API is served by the backend service.")
            return

        relative = request_path.lstrip("/")
        candidate = (self._root / relative).resolve(strict=False)

        if request_path == "/" or not candidate.exists():
            if "." not in Path(relative).name:
                self.path = "/index.html"
            else:
                self.send_error(404, "File not found")
                return

        if send_body:
            super().do_GET()
        else:
            super().do_HEAD()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve a prebuilt frontend bundle.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5173)
    parser.add_argument("--dir", default="web/dist", dest="directory")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = Path(args.directory).resolve()
    index_file = root / "index.html"
    if not index_file.exists():
        raise SystemExit(f"Frontend build output not found: {index_file}")

    handler = lambda *handler_args, **handler_kwargs: SpaStaticHandler(
        *handler_args,
        directory=str(root),
        **handler_kwargs,
    )
    server = ThreadingHttpServer((args.host, args.port), handler)
    print(f"Serving frontend from {root} on http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
