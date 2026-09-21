"""Contrats statiques et refus de publier les réserves de l'artefact."""
import copy
import hashlib
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE / "scripts"))
from registry import load, validate
from logique_artefact import verifier, exiger_publication


class ContratStatique(unittest.TestCase):
    def setUp(self):
        self.projets = load()
        self.site = json.loads((RACINE / "operations/logique-site.json").read_text())
        self.projets["logique"] = self.site

    def test_site_sans_port_ni_base(self):
        validate(self.projets)
        self.assertNotIn("port", self.site)
        self.assertNotIn("logique", json.loads((RACINE / "databases.json").read_text()))

    def test_refuse_conflits_et_racines_etrangeres(self):
        for changement in (
            {"domain": "vision.mrj.am"}, {"root": "/srv/matheval/current"},
            {"root": "/srv/logique/current; return 200"},
            {"root": "/srv/logique/../current"}, {"port": 3003},
            {"browserAuth": False}, {"prefix": "/cours"}, {"type": "inconnu"},
        ):
            projets = copy.deepcopy(self.projets)
            projets["logique"].update(changement)
            with self.subTest(changement=changement), self.assertRaises(ValueError):
                validate(projets)


class ArchiveStatique(unittest.TestCase):
    def creer(self, dossier, modifier=lambda fichiers, manifeste: None):
        reference = {cle: "a" * 40 for cle in ("application", "style", "signature")}
        fichiers = {nom: b"ressource" for nom in (
            "index.html", "app.js", "course.js", "bridge.js", "video.js",
            "katex/katex.min.js", "katex/katex.min.css",
            "assets/mrjam/Echologo.svg", "assets/mrjam/signature.css")}
        manifeste = dict(reference, portageComplet=True, typographieValidee=False,
                         hebergementConfirme=False, publicationAutorisee=False,
                         empreintes={nom: hashlib.sha256(contenu).hexdigest()
                                     for nom, contenu in fichiers.items()})
        modifier(fichiers, manifeste)
        archive = Path(dossier) / "test.zip"
        with zipfile.ZipFile(archive, "w") as z:
            for nom, contenu in fichiers.items():
                z.writestr("dist/" + nom, contenu)
            z.writestr("dist/manifeste-preparation.json", json.dumps(manifeste))
        reference["sha256"] = hashlib.sha256(archive.read_bytes()).hexdigest()
        return archive, reference

    def test_archive_verifiee_ne_devient_pas_publiable(self):
        with tempfile.TemporaryDirectory() as dossier:
            manifeste, fichiers = verifier(*self.creer(dossier))
            self.assertEqual(len(fichiers), 10)
            with self.assertRaisesRegex(ValueError, "typographieValidee"):
                exiger_publication(manifeste)

    def test_refuse_archive_et_fichier_alteres(self):
        with tempfile.TemporaryDirectory() as dossier:
            archive, reference = self.creer(dossier)
            reference["sha256"] = "0" * 64
            with self.assertRaisesRegex(ValueError, "empreinte de l'archive"):
                verifier(archive, reference)
            archive, reference = self.creer(
                dossier, lambda fichiers, _: fichiers.update({"app.js": b"autre"}))
            with self.assertRaisesRegex(ValueError, "Fichier altéré"):
                verifier(archive, reference)

    def test_refuse_evasion_et_fichier_non_repertorie(self):
        for nom in ("../hors-dist", ".env", "supplement.js"):
            with self.subTest(nom=nom), tempfile.TemporaryDirectory() as dossier:
                archive, reference = self.creer(
                    dossier, lambda fichiers, _: fichiers.update({nom: b"interdit"}))
                with self.assertRaises(ValueError):
                    verifier(archive, reference)


if __name__ == "__main__":
    unittest.main()
