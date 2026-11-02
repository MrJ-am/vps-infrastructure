#!/usr/bin/env python3
"""Fournisseur local d'embeddings, interchangeable via le contrat HTTP.

Le modèle doit être un snapshot local complet. Aucun téléchargement au démarrage,
aucun journal du contenu. Seul le contenu est vectorisé, jamais les alias.
"""
import argparse
import hashlib
import json
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer


def empreinte_modele(dossier):
    empreinte = hashlib.sha256()
    for chemin in sorted(Path(dossier).rglob('*')):
        if chemin.is_file() and '.cache' not in chemin.parts:
            empreinte.update(str(chemin.relative_to(dossier)).encode())
            with chemin.open('rb') as fichier:
                for bloc in iter(lambda: fichier.read(1024 * 1024), b''):
                    empreinte.update(bloc)
    return empreinte.hexdigest()


class Fournisseur:
    def __init__(self, dossier):
        from sentence_transformers import SentenceTransformer
        self.modele = SentenceTransformer(str(dossier), device='cpu', local_files_only=True)
        # La stratégie de fenêtrage fait partie de l'identité des vecteurs.
        self.identite = 'contenu-fenetres-1:' + empreinte_modele(dossier)

    def calculer(self, contenu):
        import numpy as np
        tokenizer = self.modele.tokenizer
        ids = tokenizer.encode(contenu, add_special_tokens=False)
        capacite = self.modele.max_seq_length - tokenizer.num_special_tokens_to_add()
        if capacite < 16:
            raise ValueError('Capacité de modèle invalide')
        # Chaque token du contenu complet est couvert, même au-delà de la fenêtre.
        pas = max(1, capacite - 16)
        textes = [tokenizer.decode(ids[debut:debut+capacite], skip_special_tokens=True)
                  for debut in range(0, len(ids), pas)]
        vecteurs = self.modele.encode(textes, normalize_embeddings=True, batch_size=8)
        moyenne = np.mean(vecteurs, axis=0)
        norme = np.linalg.norm(moyenne)
        if not np.isfinite(norme) or norme == 0:
            raise ValueError('Vecteur invalide')
        return dict(modele=self.identite, embedding=(moyenne / norme).tolist())


def servir(fournisseur, port):
    class Requete(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            try:
                taille = int(self.headers.get('Content-Length', '0'))
                if self.path != '/embedding' or not 0 < taille <= 65536:
                    raise ValueError('Requête invalide')
                donnees = json.loads(self.rfile.read(taille))
                contenu = donnees['contenu']
                if not isinstance(contenu, str) or not 1 <= len(contenu) <= 12000 or not contenu.strip():
                    raise ValueError('Contenu invalide')
                resultat = fournisseur.calculer(contenu)
                code = 200
            except (ValueError, KeyError, TypeError):
                resultat, code = {'erreur': 'contenu_invalide'}, 400
            except Exception:
                resultat, code = {'erreur': 'embedding_indisponible'}, 503
            corps = json.dumps(resultat, allow_nan=False).encode()
            self.send_response(code)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(corps)))
            self.end_headers()
            self.wfile.write(corps)

    HTTPServer(('127.0.0.1', port), Requete).serve_forever()


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--modele', type=Path, required=True)
    cli.add_argument('--port', type=int, default=39004)
    args = cli.parse_args()
    servir(Fournisseur(args.modele), args.port)

