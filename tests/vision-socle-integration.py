"""Une source brute modifiée ne doit pas remplacer la source Nix active.

Source synthétique seulement ; aucune construction de système ou activation.
NIX_PATH doit désigner le Nixpkgs épinglé de qualification.
"""
import json
from pathlib import Path
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]


def nix(*args):
    return json.loads(subprocess.check_output(['nix-instantiate', '--eval',
        '--strict', '--json', *args], text=True))


with tempfile.TemporaryDirectory(prefix='vision-socle-') as temporaire:
    r = Path(temporaire); source = r/'source'; (source/'scripts').mkdir(parents=True)
    for nom in ('embeddings.py', 'backfill_embeddings.py'):
        (source/'scripts'/nom).write_text('# Fournisseur synthétique, jamais exécuté.\n')
    expression = 'builtins.path { path = builtins.toPath '+json.dumps(str(source))+'; name = "vision-fournisseur-c0bfcac"; }'
    actif = nix('--read-write-mode', '--expr', expression)
    configuration = r/'configuration.nix'
    configuration.write_text('{ imports = [ (builtins.toPath '+json.dumps(str(ROOT/'hosts/hostinger/logique.nix'))+
        ') (builtins.toPath '+json.dumps(str(ROOT/'vendor/vision-embeddings/embeddings.nix'))+
        ') ]; services.visionEmbeddings.enable = true; services.visionEmbeddings.source = '+expression+'; }\n')
    arguments = [str(ROOT/'scripts/vision-multiutilisateur-config.nix'), '--argstr', 'configuration', str(configuration)]
    initial = nix(*arguments)
    # Même code ; un répertoire ajouté change l'archive brute et sa génération.
    (source/'repertoire-ajoute').mkdir()
    brut = nix(*arguments)
    assert brut['systeme'] != initial['systeme'], 'Dérive synthétique non reproduite'
    epingle = nix(*arguments, '--argstr', 'fournisseur', actif)
    assert epingle['systeme'] == initial['systeme'], 'Génération exacte non rétablie'
    assert epingle['fournisseur_source'] == actif
    assert epingle['postgres_majeure'] == '17' and epingle['postgres_tcp'] is False and epingle['postgres_ecoute'] == ''
    print(json.dumps({'source_brute_derivee': True, 'generation_exacte_retablie': True,
        'source_active_conservee': True, 'postgres_sans_tcp': True, 'activation': False}))
