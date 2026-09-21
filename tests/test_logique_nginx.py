"""Servir les locations Nix réelles avec un Nginx jetable, sans accès au VPS."""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time
import unittest
import urllib.error
import urllib.request

RACINE = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("nginx") and shutil.which("nix-instantiate"),
                     "Nginx et Nix requis ; test obligatoire dans la CI")
class ServiceStatique(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporaire = tempfile.TemporaryDirectory()
        cls.dossier = Path(cls.temporaire.name)
        cls.dossier.chmod(0o755)
        cls.fichiers = cls.dossier / "www"
        cls.fichiers.mkdir()
        for nom, contenu in {
            "index.html": "<!doctype html><title>Logique</title>",
            "app.js": "const cours = true;",
            "katex/katex.min.js": "const katex = true;",
            "assets/mrjam/signature.css": "/* signature */",
            "manifeste-preparation.json": '{"application":"test"}',
            ".env": "NE_JAMAIS_SERVIR",
        }.items():
            p = cls.fichiers / nom
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(contenu)
        expression = '(import ./lib/virtual-hosts.nix) { logique = builtins.fromJSON (builtins.readFile ./operations/logique-site.json); }'
        generation = subprocess.run(
            ["nix-instantiate", "--eval", "--strict", "--json", "--expr", expression],
            cwd=RACINE, check=True, text=True, capture_output=True)
        hote = json.loads(generation.stdout)["logique.echos.systems"]
        locations = []
        for chemin, options in hote["locations"].items():
            directives = "\n".join(
                f"{directive} {options[nom]};" for nom, directive in (
                    ("index", "index"), ("tryFiles", "try_files"), ("return", "return")
                ) if nom in options)
            locations.append(f"location {chemin} {{\n{directives}\n}}")
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            cls.port = s.getsockname()[1]
        configuration = cls.dossier / "nginx.conf"
        utilisateur = "user root;\n" if os.geteuid() == 0 else ""
        configuration.write_text(utilisateur + f"""
            daemon off;
            pid {cls.dossier}/nginx.pid;
            error_log {cls.dossier}/erreurs.log;
            events {{}}
            http {{
              access_log off;
              types {{ text/html html; application/javascript js; text/css css; application/json json; }}
              server {{
                listen 127.0.0.1:{cls.port};
                server_name logique.echos.systems;
                root {cls.fichiers};
                {hote["extraConfig"]}
                {"".join(locations)}
              }}
            }}
        """)
        commande = ["nginx", "-p", str(cls.dossier), "-c", str(configuration)]
        subprocess.run(commande + ["-t"], check=True, capture_output=True)
        cls.processus = subprocess.Popen(commande, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(100):
            try:
                with socket.create_connection(("127.0.0.1", cls.port), timeout=0.1):
                    return
            except OSError:
                if cls.processus.poll() is not None:
                    raise RuntimeError((cls.dossier / "erreurs.log").read_text())
                time.sleep(0.02)
        cls.processus.terminate()
        cls.processus.wait(timeout=5)
        raise RuntimeError("Nginx n'a pas démarré.")

    @classmethod
    def tearDownClass(cls):
        cls.processus.terminate()
        cls.processus.wait(timeout=5)
        cls.temporaire.cleanup()

    def lire(self, chemin):
        try:
            reponse = urllib.request.urlopen(f"http://127.0.0.1:{self.port}{chemin}", timeout=3)
        except urllib.error.HTTPError as e:
            reponse = e
        with reponse:
            return reponse.status, reponse.headers, reponse.read()

    def test_html_et_ressources_sans_cache_permanent(self):
        for chemin in ("/", "/?parcours=contrats", "/app.js", "/katex/katex.min.js",
                       "/assets/mrjam/signature.css", "/manifeste-preparation.json"):
            with self.subTest(chemin=chemin):
                statut, entetes, contenu = self.lire(chemin)
                self.assertEqual(statut, 200)
                self.assertTrue(contenu)
                self.assertEqual(entetes["Cache-Control"], "no-cache")
                self.assertEqual(entetes["X-Content-Type-Options"], "nosniff")
        self.assertEqual(self.lire("/app.js")[1].get_content_type(), "application/javascript")

    def test_absences_et_fichiers_caches_ne_deviennent_pas_du_html_applicatif(self):
        for chemin in ("/absent.js", "/katex/absent.woff2", "/assets/absent.svg",
                       "/.env", "/.git/config", "/cours/inconnu"):
            with self.subTest(chemin=chemin):
                statut, _, contenu = self.lire(chemin)
                self.assertEqual(statut, 404)
                self.assertNotIn(b"NE_JAMAIS_SERVIR", contenu)
                self.assertNotIn(b"<title>Logique</title>", contenu)


if __name__ == "__main__":
    unittest.main()
