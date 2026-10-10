"""Une entrée persistante ne doit pas importer le lien qu'elle remplace."""
import hashlib
import json
from pathlib import Path
import re

COURANTE = Path('/etc/nixos/configuration.nix')


def exiger(condition):
    if not condition: raise ValueError('Référence de configuration refusée')


def reference_originale(original, copie):
    original, copie = Path(original), Path(copie)
    for p in (original,copie): exiger(p.is_absolute() and re.fullmatch(r'/[A-Za-z0-9/_.-]+\.nix',str(p)))
    exiger(copie != COURANTE)
    return copie if original == COURANTE else original


def entree(original, module, fournisseur):
    for p in (original,module): exiger(re.fullmatch(r'/[A-Za-z0-9/_.-]+\.nix',str(p)))
    exiger(re.fullmatch(r'/nix/store/[0-9abcdfghijklmnpqrsvwxyz]{32}-[A-Za-z0-9+._-]+',fournisseur))
    return '{ lib, ... }: { imports = [ '+json.dumps(str(original))+' '+json.dumps(str(module))+' ];\n'+ \
        'infrastructure.amorcageIdentite.enable = true;\n'+ \
        'services.visionEmbeddings.source = lib.mkForce (builtins.storePath '+json.dumps(fournisseur)+');\n}\n'


def reparer(ancien, sauvegarde, empreinte, essai, module, fournisseur):
    exiger(re.fullmatch('[a-f0-9]{64}',empreinte) and hashlib.sha256(sauvegarde.encode()).hexdigest() == empreinte)
    nouveau = entree(Path(essai)/'configuration-avant.nix',module,fournisseur)
    exiger(ancien in (entree(COURANTE,module,fournisseur),nouveau))
    return nouveau
