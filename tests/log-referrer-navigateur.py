"""Régression navigateur : POST réellement reçu, uniquement sur loopback.

Ni credentials, ni requête à la production. La politique interdit aussi la
fuite du chemin/query synthétiques dans Referer, sans neutraliser le CSRF.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import queue
import threading
from playwright.sync_api import sync_playwright


def verifier():
    events = queue.Queue()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            if self.path.startswith('/ancien'):
                self.send_header('Referrer-Policy', 'origin')
                self.send_header('Referrer-Policy', 'no-referrer')
            else: self.send_header('Referrer-Policy', 'strict-origin')
            self.end_headers()
            self.wfile.write(b'<form action="/begin" method="post"><input name="username" value="fixture"><button>Login</button></form>')
        def do_POST(self):
            self.rfile.read(int(self.headers.get('Content-Length', '0')))
            origin = self.headers.get('Origin'); referrer = self.headers.get('Referer')
            expected = f'http://127.0.0.1:{self.server.server_port}'
            status = 200 if origin == expected else 403
            events.put((origin, referrer, status))
            self.send_response(status); self.end_headers(); self.wfile.write(b'fixture')
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    root = f'http://127.0.0.1:{server.server_port}'
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=os.environ['PLAYWRIGHT_CHROMIUM_EXECUTABLE'], headless=True)
            try:
                for path in ['/ancien?secret=synthetique', '/corrige?secret=synthetique']:
                    page = browser.new_page()
                    page.goto(root+path, wait_until='domcontentloaded')
                    page.locator('form').evaluate('(f)=>f.requestSubmit()')
                    origin, referer, status = events.get(timeout=10)
                    if path.startswith('/ancien'):
                        assert origin == 'null' and status == 403 and referer is None
                    else:
                        assert origin == root and status == 200 and referer == root+'/'
                    page.close()
                # Une provenance étrangère ne devient pas acceptable.
                request = browser.new_context().request
                response = request.post(root+'/begin', headers={'Origin':'https://foreign.example.test'}, data='username=fixture')
                assert response.status == 403
                assert events.get(timeout=10)[2] == 403
            finally: browser.close()
    finally: server.shutdown(); server.server_close()
    print(json.dumps({'ancien_refuse':True, 'corrige_accepte':True, 'origine_etrangere_refusee':True,
                      'chemin_et_query_non_transmis':True, 'production':False}))

if __name__ == '__main__': verifier()
