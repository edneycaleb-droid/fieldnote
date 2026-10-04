"""Serve only this synthetic WebMCP lab on IPv4 loopback. Python 3.10+."""
from __future__ import annotations
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
import webbrowser

ROOT = Path(__file__).resolve().parent
ASSETS = {
    '/': ('index.html', 'text/html; charset=utf-8'),
    '/index.html': ('index.html', 'text/html; charset=utf-8'),
    '/app.mjs': ('app.mjs', 'text/javascript; charset=utf-8'),
    '/core.mjs': ('core.mjs', 'text/javascript; charset=utf-8'),
    '/workflows.mjs': ('workflows.mjs', 'text/javascript; charset=utf-8'),
}
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self._serve(False)
    def do_HEAD(self):
        self._serve(True)
    def _serve(self, head_only):
        port = self.server.server_address[1]
        if self.headers.get('Host') not in {f'127.0.0.1:{port}', f'localhost:{port}'}:
            self.send_error(403, 'Loopback Host required')
            return
        try:
            asset = ASSETS.get(urlsplit(self.path).path)
        except ValueError:
            asset = None
        if asset is None:
            self.send_error(404)
            return
        name, mime = asset
        path = ROOT / name
        if path.is_symlink() or path.resolve().parent != ROOT:
            self.send_error(403)
            return
        try:
            content = path.read_bytes()
        except OSError:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(content)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Permissions-Policy', 'tools=(self)')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' blob:; connect-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
        self.end_headers()
        if not head_only:
            self.wfile.write(content)
    def log_message(self, _format, *args):
        pass  # Avoid recording URL/query data.

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--open', action='store_true', help='Open the default browser after binding successfully')
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error('--port must be between 1024 and 65535')
    try:
        server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    except OSError as error:
        parser.exit(1, f'Cannot start loopback server: {error}\n')
    url = f'http://127.0.0.1:{args.port}'
    print(f'WebMCP lab: {url}\nLocal synthetic data only. Stop with Ctrl+C.', flush=True)
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
if __name__ == '__main__':
    main()
