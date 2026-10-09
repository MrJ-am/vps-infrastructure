"""Diagnostic NixOS en lecture seule, sans secret ni contenu applicatif.

À transmettre sur stdin depuis le workflow d'audit existant. N'active aucune
génération, ne construit aucun paquet et ne consulte aucune base de données.
"""
import json
import hashlib
import os
from pathlib import Path
import re
import subprocess


NIXPKGS = '/nix/store/81s59zcy998ym4b36ayr29cjc9yhma5n-nixos-26.05.8639.c5c4a43b0e80/nixos'
ATTENDU = '/nix/store/y1azkcagkf54nq5vjn4j16g5v1c61c4c-nixos-system-nixos-26.05.8639.c5c4a43b0e80'
SOURCE = '/root/vision-semantique/32a4c3d2ad0e39568fe16d7acdb2472a7f095fc2/source/hosts/hostinger/vision-semantique.nix'
UNITES = ('sshd', 'nginx', 'postgresql', 'postgresql-setup', 'matheval',
    'vision', 'vision-migrate', 'mrj-auth', 'vision-embeddings',
    'vision-embeddings-backfill', 'postgresqlBackup-matheval', 'postgresqlBackup-vision')
EXPRESSION = '''{ configuration, classique ? false, fournisseur ? null }:
let
  lib = import <nixpkgs/lib>;
  c = if classique then (import <nixpkgs/nixos> {
    system = "x86_64-linux"; configuration = import (builtins.toPath configuration);
  }).config else (import <nixpkgs/nixos/lib/eval-config.nix> {
    system = "x86_64-linux"; modules = [ (builtins.toPath configuration) ]
      ++ lib.optional (fournisseur != null) ({ lib, ... }: {
        services.visionEmbeddings.source = lib.mkForce (builtins.storePath fournisseur);
      });
  }).config;
in {
  systeme = toString c.system.build.toplevel;
  postgres_majeure = (import <nixpkgs/lib>).versions.major c.services.postgresql.package.version;
  postgres_tcp = c.services.postgresql.enableTCPIP;
  postgres_ecoute = c.services.postgresql.settings.listen_addresses;
  fournisseur_source = if c.services ? visionEmbeddings && c.services.visionEmbeddings.enable
    then toString c.services.visionEmbeddings.source else null;
  unites = lib.genAttrs [ "sshd" "nginx" "postgresql" "postgresql-setup" "matheval"
    "vision" "vision-migrate" "mrj-auth" "vision-embeddings" "vision-embeddings-backfill"
    "postgresqlBackup-matheval" "postgresqlBackup-vision" ]
    (nom: if builtins.hasAttr (nom + ".service") c.systemd.units
      then c.systemd.units."${nom}.service".text else null);
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


def lire_evaluation(configuration, classique, fournisseur=None):
    args = ['nix-instantiate', '--eval', '--strict', '--json',
        '--expr', EXPRESSION, '--argstr', 'configuration', configuration,
        '--arg', 'classique', 'true' if classique else 'false',
        '-I', 'nixpkgs=' + NIXPKGS]
    if fournisseur is not None: args += ['--argstr', 'fournisseur', fournisseur]
    r = subprocess.run(args, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, timeout=240, check=False)
    if r.returncode: return None
    return json.loads(r.stdout)


def evaluer(configuration, classique, actif):
    c = lire_evaluation(configuration, classique)
    return resume(c, actif) if c is not None else {'evaluation_reussie': False}


def comparer_unites(c):
    resultat = {}
    for nom in UNITES:
        p = Path('/run/current-system/etc/systemd/system') / (nom + '.service')
        attendu = c['unites'][nom]
        if not p.exists(): resultat[nom] = 'absente' if attendu is not None else 'conforme'
        else:
            if not str(p.resolve()).startswith('/nix/store/'): raise ValueError('Unité hors store')
            resultat[nom] = 'conforme' if attendu is not None and p.read_bytes() == attendu.encode() else 'differente'
    return resultat


def source_fournisseur_active():
    p = Path('/run/current-system/etc/systemd/system/vision-embeddings.service')
    if not p.exists(): return None
    if not str(p.resolve()).startswith('/nix/store/'): raise ValueError('Unité hors store')
    sources = re.findall(r'(/nix/store/[0-9a-z]{32}-vision-fournisseur-c0bfcac)/scripts/embeddings\.py', p.read_text())
    return sources[0] if len(set(sources)) == 1 else None


def comparer_sources(actif, calcule):
    motif = r'/nix/store/[0-9a-z]{32}-vision-fournisseur-c0bfcac'
    if not all(isinstance(p, str) and re.fullmatch(motif, p) for p in (actif, calcule)):
        return {'sources_identifiees': False}
    chemins = ('scripts/embeddings.py', 'scripts/backfill_embeddings.py')
    def empreinte(p): return hashlib.sha256(p.read_bytes()).digest()
    def arbre(p): return sorted(str(x.relative_to(p)) for x in p.rglob('*'))
    presences = {p: {'actif': (Path(actif)/p).is_file(), 'calcule': (Path(calcule)/p).is_file()} for p in chemins}
    complets = all(v['actif'] and v['calcule'] for v in presences.values())
    return {'sources_identifiees': True, 'chemin_identique': actif == calcule,
        'source_active': actif, 'source_calculee': calcule, 'scripts_presents': presences,
        'deux_scripts_identiques': complets and all(empreinte(Path(actif)/p) == empreinte(Path(calcule)/p) for p in chemins),
        'arborescence_identique': Path(actif).is_dir() and Path(calcule).is_dir() and arbre(Path(actif)) == arbre(Path(calcule))}


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
    try:
        c = lire_evaluation('/etc/nixos/configuration.nix', False)
        if c is not None:
            resultat['unites'] = comparer_unites(c)
            source = source_fournisseur_active()
            resultat['fournisseur'] = comparer_sources(source, c['fournisseur_source'])
            if source is not None:
                epingle = lire_evaluation('/etc/nixos/configuration.nix', False, source)
                resultat['fournisseur_actif_epingle'] = resume(epingle, actif) if epingle else {'evaluation_reussie': False}
    except Exception:
        resultat['comparaison_unites_reussie'] = False
    print(json.dumps(resultat, ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print(json.dumps({'audit_socle': 1, 'diagnostic_refuse': True, 'activation': False}))
        raise SystemExit(1)
