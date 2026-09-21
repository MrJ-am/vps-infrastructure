"""Contrôles de l'artefact et du routage exact de la nouvelle interface."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time
import unittest
import urllib.request
import urllib.error

RACINE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('publication_vision', RACINE / 'scripts/vision-interface-deployer.py')
publication = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publication)


class Artefact(unittest.TestCase):
    def test_corruption_et_chemin_hors_artefact(self):
        with tempfile.TemporaryDirectory() as temporaire:
            dossier = Path(temporaire)
            noms = ['app.html', 'app.js', 'app.css', 'assets/mrjam/MrJamSignature.woff2']
            for nom in noms:
                p = dossier / nom
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(b'fixture isolee')
            manifeste = {'formatVersion': 1, 'revisionApplication': 'a' * 40,
                'revisionStyle': 'b' * 40, 'revisionSignature': 'c' * 40,
                'fichiers': {n: publication.empreinte(dossier / n) for n in noms}}
            (dossier / 'manifest.json').write_text(json.dumps(manifeste))
            publication.verifier_artefact(dossier)
            (dossier / 'app.js').write_bytes(b'autre contenu')
            with self.assertRaises(RuntimeError): publication.verifier_artefact(dossier)
            (dossier / 'app.js').write_bytes(b'fixture isolee')
            (dossier / 'fuite').symlink_to('/etc')
            with self.assertRaises(RuntimeError): publication.verifier_artefact(dossier)


@unittest.skipUnless(shutil.which('nginx') and shutil.which('nix-instantiate'), 'Nginx et Nix requis dans la CI')
class Routage(unittest.TestCase):
    def test_routes_et_csp_reelles(self):
        with tempfile.TemporaryDirectory() as temporaire:
            dossier = Path(temporaire)
            dossier.chmod(0o755)
            for nom, contenu in {'app.html': '<title>Vision</title>', 'app.js': 'const vision = true;',
                    'app.css': '/* style */', 'manifest.json': '{}', 'assets/mrjam/Signature.woff2': 'police', '.env': 'PRIVE'}.items():
                p = dossier / 'www' / nom
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(contenu)
            expression = '(import ./apps/vision-interface.nix { lib = {}; }).services.nginx.virtualHosts."vision.mrj.am".locations'
            locs = json.loads(subprocess.check_output(['nix-instantiate', '--eval', '--strict', '--json', '--expr', expression], cwd=RACINE, text=True))
            locations = ''.join('location ' + nom + ' { root ' + str(dossier / 'www') + '; try_files ' + opts['tryFiles'] + '; ' + opts['extraConfig'] + ' }' for nom, opts in locs.items())
            with socket.socket() as s:
                s.bind(('127.0.0.1', 0)); port = s.getsockname()[1]
            configuration = dossier / 'nginx.conf'
            configuration.write_text(('user root; ' if os.geteuid() == 0 else '') + f'''daemon off; pid {dossier}/pid; error_log {dossier}/error.log; events {{}} http {{ access_log off; types {{ text/html html; application/javascript js; text/css css; font/woff2 woff2; }} server {{ listen 127.0.0.1:{port}; {locations} location / {{ return 418; }} }} }}''')
            processus = subprocess.Popen(['nginx', '-p', str(dossier), '-c', str(configuration)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                for _ in range(100):
                    try:
                        with socket.create_connection(('127.0.0.1', port), timeout=.1): break
                    except OSError: time.sleep(.02)
                def lire(chemin):
                    try: r = urllib.request.urlopen(f'http://127.0.0.1:{port}' + chemin)
                    except urllib.error.HTTPError as e: r = e
                    with r: return r.status, r.headers, r.read()
                for chemin in ('/', '/app.js', '/app.css', '/interface-manifest.json', '/assets/mrjam/Signature.woff2'):
                    statut, headers, _ = lire(chemin)
                    self.assertEqual(statut, 200)
                    self.assertEqual(headers['Cache-Control'], 'no-cache')
                    self.assertIn("style-src 'self' 'unsafe-inline'", headers['Content-Security-Policy'])
                    self.assertIn("font-src 'self'", headers['Content-Security-Policy'])
                    self.assertNotIn("script-src 'self' 'unsafe-inline'", headers['Content-Security-Policy'])
                self.assertEqual(lire('/assets/mrjam/absent.woff2')[0], 404)
                for chemin in ('/auth/session', '/api/web/list', '/mcp', '/.env'):
                    self.assertEqual(lire(chemin)[0], 418, 'La nouvelle interface ne doit pas intercepter ' + chemin)
            finally:
                processus.terminate(); processus.wait(timeout=5)


if __name__ == '__main__':
    unittest.main()
