"""Diagnostic NixOS en lecture seule, sans secret ni contenu applicatif.

À transmettre sur stdin depuis le workflow d'audit existant. N'active aucune
génération, ne construit aucun paquet et ne consulte aucune base de données.
"""
import json
import os
from pathlib import Path
import re
import subprocess


NIXPKGS = '/nix/store/81s59zcy998ym4b36ayr29cjc9yhma5n-nixos-26.05.8639.c5c4a43b0e80/nixos'
ATTENDU = '/nix/store/y1azkcagkf54nq5vjn4j16g5v1c61c4c-nixos-system-nixos-26.05.8639.c5c4a43b0e80'
SOURCE = '/root/vision-semantique/32a4c3d2ad0e39568fe16d7acdb2472a7f095fc2/source/hosts/hostinger/vision-semantique.nix'
EXPRESSION = '''{ configuration, classique ? false }:
let
  c = if classique then (import <nixpkgs/nixos> {
    system = "x86_64-linux"; configuration = import (builtins.toPath configuration);
  }).config else (import <nixpkgs/nixos/lib/eval-config.nix> {
    system = "x86_64-linux"; modules = [ (builtins.toPath configuration) ];
  }).config;
in {
  systeme = toString c.system.build.toplevel;
  postgres_majeure = (import <nixpkgs/lib>).versions.major c.services.postgresql.package.version;
  postgres_tcp = c.services.postgresql.enableTCPIP;
  postgres_ecoute = c.services.postgresql.settings.listen_addresses;
}'''


def generation(chemin):
    if not isinstance(chemin, str) or not re.fullmatch(
            r'/nix/store/[0-9a-z]{32}-nixos-system-[A-Za-z0-9._+-]{1,100}', chemin):
        raise ValueError('Métadonnée de génération inattendue')
    return chemin


def resume(configuration, actif):
    """Liste fermée : ne restitue jamais les autres champs de configuration."""
    systeme = generation(configuration['systeme'])
    return {'evaluation_reussie': True, 'generation': systeme,
        'generation_identique': systeme == actif,
        'postgres_17': configuration['postgres_majeure'] == '17',
        'postgres_sans_tcp': configuration['postgres_tcp'] is False,
        'postgres_ecoute_vide': configuration['postgres_ecoute'] == ''}


def evaluer(configuration, classique, actif):
    r = subprocess.run(['nix-instantiate', '--eval', '--strict', '--json',
        '--expr', EXPRESSION, '--argstr', 'configuration', configuration,
        '--arg', 'classique', 'true' if classique else 'false',
        '-I', 'nixpkgs=' + NIXPKGS], stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, timeout=240, check=False)
    if r.returncode: return {'evaluation_reussie': False}
    return resume(json.loads(r.stdout), actif)


def main():
    if os.geteuid() != 0: raise ValueError('Audit Actions root requis')
    actif = generation(str(Path('/run/current-system').resolve()))
    demarrage = generation(str(Path('/nix/var/nix/profiles/system').resolve()))
    resultat = {'audit_socle': 1, 'generation_active': actif,
        'generation_attendue': ATTENDU, 'generation_conforme_audit': actif == ATTENDU,
        'demarrage_identique': demarrage == actif, 'activation': False}
    variantes = [('entree', '/etc/nixos/configuration.nix', False),
        ('source_installee', SOURCE, False),
        ('import_classique', '/etc/nixos/configuration.nix', True)]
    for nom, chemin, classique in variantes:
        try:
            resultat[nom] = evaluer(chemin, classique, actif)
        except Exception:
            # Les erreurs Nix/Python ne publient ni chemin arbitraire ni donnée.
            resultat[nom] = {'evaluation_reussie': False}
    print(json.dumps(resultat, ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print(json.dumps({'audit_socle': 1, 'diagnostic_refuse': True, 'activation': False}))
        raise SystemExit(1)
