"""Serve the standalone storefront preview at its sample page URLs.

This is a local design preview. It does not run Django or process orders.
"""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from mimetypes import guess_type
from pathlib import Path
from urllib.parse import urlsplit


PREVIEW = Path(__file__).resolve().parent.parent / "storefront-preview.html"
STATIC_ROOT = PREVIEW.parent / "static"
STATIC_FILES = {"/static/preview.css", "/static/preview.js", "/static/annam-preview-catalog.json"}
ASSET_PREFIX = "/static/images/annam/"
PAGES = {
    "/",
    "/storefront-preview.html",
    "/menu/",
    "/cart/",
    "/p/delivery-cashback/",
    "/p/refund-policy/",
    "/p/about/",
}


class PreviewHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlsplit(self.path).path
        if path in STATIC_FILES:
            asset = STATIC_ROOT / Path(path).name
            content = asset.read_bytes()
            content_type = (guess_type(asset.name)[0] or "application/octet-stream") + "; charset=utf-8"
        elif path.startswith(ASSET_PREFIX):
            name = path.removeprefix(ASSET_PREFIX)
            asset = STATIC_ROOT / "images" / "annam" / name
            if name != Path(name).name or not asset.is_file():
                self.send_error(404, "Preview asset not found")
                return
            content = asset.read_bytes()
            content_type = guess_type(asset.name)[0] or "application/octet-stream"
        elif path in PAGES:
            content = PREVIEW.read_bytes()
            content_type = "text/html; charset=utf-8"
        else:
            self.send_error(404, "Preview page not found")
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 8765), PreviewHandler)
    print("Preview available at http://127.0.0.1:8765/", flush=True)
    server.serve_forever()
