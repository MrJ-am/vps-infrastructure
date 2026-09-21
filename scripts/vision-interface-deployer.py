#!/usr/bin/env python3
"""Publication de l'interface seule, avec génération conservée et retour autonome."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import time

SERVICES = ('sshd', 'nginx', 'postgresql', 'matheval', 'vision', 'mrj-auth')
RACINE = Path('/root/vision-interface-operations')
COURANT = Path('/srv/vision-interface/current')
ENTREE = Path('/etc/nixos/configuration.nix')


def exiger(condition, message):
    if not condition:
        raise RuntimeError(message)


def executer(*arguments, visible=False):
    resultat = subprocess.run([str(a) for a in arguments], text=True,
        stdout=None if visible else subprocess.PIPE, stderr=subprocess.PIPE)
    exiger(resultat.returncode == 0, f'{Path(str(arguments[0])).name} : {(resultat.stderr or "")[-1500:]}')
    return resultat.stdout


def empreinte(chemin):
    return hashlib.sha256(Path(chemin).read_bytes()).hexdigest()


def enregistrer(chemin, objet):
    chemin = Path(chemin)
    temporaire = chemin.with_suffix('.nouveau')
    temporaire.write_text(json.dumps(objet, ensure_ascii=False, indent=2) + '\n')
    os.replace(temporaire, chemin)


def chemins(revision):
    exiger(re.fullmatch('[0-9a-f]{40}', revision), 'Révision invalide')
    return RACINE / revision


def services():
    for nom in SERVICES:
        exiger(executer('systemctl', 'is-active', nom).strip() == 'active', 'Service inactif : ' + nom)
    for nom in ('vision', 'matheval'):
        executer('systemctl', 'is-active', 'postgresqlBackup-' + nom + '.timer')


def etat():
    return {
        'actif': str(Path('/run/current-system').resolve()),
        'demarrage': str(Path('/nix/var/nix/profiles/system').resolve()),
        'configuration': empreinte(ENTREE),
        'vision': str(Path('/srv/vision/current').resolve()),
        'matheval': str(Path('/srv/matheval/current').resolve()),
        'interface': str(COURANT.resolve()) if COURANT.is_symlink() else None,
    }


def verifier_artefact(dossier):
    manifeste = json.loads((dossier / 'manifest.json').read_text())
    exiger(manifeste['formatVersion'] == 1, 'Format de manifeste inconnu')
    for cle in ('revisionApplication', 'revisionStyle', 'revisionSignature'):
        exiger(re.fullmatch('[0-9a-f]{40}', manifeste[cle]), 'Révision de manifeste invalide')
    exiger(not any(p.is_symlink() for p in dossier.rglob('*')), 'Lien symbolique dans l’artefact')
    reels = {str(p.relative_to(dossier)) for p in dossier.rglob('*') if p.is_file()}
    exiger(reels == set(manifeste['fichiers']) | {'manifest.json'}, 'Jeu de fichiers différent du manifeste')
    for nom, attendu in manifeste['fichiers'].items():
        p = dossier / nom
        exiger(not p.is_symlink() and p.resolve().is_relative_to(dossier.resolve()), 'Chemin non régulier')
        exiger(empreinte(p) == attendu, 'Empreinte différente : ' + nom)
    exiger({'app.html', 'app.js', 'app.css', 'assets/mrjam/MrJamSignature.woff2'} <= reels, 'Interface incomplète')
    return manifeste


def evaluer(source, configuration, nixpkgs):
    return json.loads(executer('nix-instantiate', '--eval', '--strict', '--json',
        source / 'scripts/vision-interface-config.nix', '--argstr', 'configuration',
        configuration, '-I', 'nixpkgs=' + nixpkgs))


def preparer(revision):
    dossier = chemins(revision)
    source = dossier / 'source'
    exiger(not (dossier / 'prepare.json').exists(), 'Cette opération est déjà préparée')
    exiger(not ENTREE.is_symlink(), 'Entrée NixOS symbolique : préparation adaptée nécessaire')
    avant = etat()
    exiger(avant['actif'] == avant['demarrage'], 'Une autre bascule système est en cours')
    exiger(avant['interface'] is None, 'L’interface possède déjà une publication : opération distincte requise')
    services()
    manifeste = verifier_artefact(source / 'vendor/vision-interface')
    nixpkgs = executer('nix-instantiate', '--find-file', 'nixpkgs').strip()
    installe = Path('/etc/nixos/vps-infrastructure') / ('vision-interface-' + revision)
    exiger(not installe.exists(), 'Chemin de préparation déjà utilisé')
    shutil.copytree(source, installe)
    shutil.copy2(ENTREE, dossier / 'configuration-avant.nix')
    # L'entrée installée conserve ses chemins absolus : le site Logique et toute
    # autre évolution déjà active sont inclus, sans reconstruire une branche ancienne.
    shutil.copy2(ENTREE, installe / 'configuration-avant.nix')
    (installe / 'configuration-interface.nix').write_text(
        '{ imports = [ ./configuration-avant.nix ./apps/vision-interface.nix ]; }\n')
    a = evaluer(installe, ENTREE, nixpkgs)
    b = evaluer(installe, installe / 'configuration-interface.nix', nixpkgs)
    exiger(a['systeme'] == avant['actif'], 'Les sources actives ne reproduisent pas le système courant')
    exiger(a['invariant'] == b['invariant'], 'Une configuration extérieure à l’interface changerait')
    registre = json.loads((source / 'projects.json').read_text())
    if 'logique.echos.systems' in a['invariant']['sites']:
        registre['logique'] = json.loads((source / 'operations/logique-site.json').read_text())
    domaines = {d for site in registre.values() for d in [site['domain'], *site['aliases']]}
    exiger(domaines == set(a['invariant']['sites']), 'Un site actif manque au registre de contrôle')
    enregistrer(dossier / 'registre.json', registre)
    executer(sys.executable, source / 'scripts/probe.py', '--registry', dossier / 'registre.json',
        '--output', dossier / 'http-avant.json', visible=True)
    for nom in ('vision', 'matheval'):
        with (dossier / (nom + '-avant.dump.age')).open('wb') as sortie:
            subprocess.run([nom + '-backup'], stdout=sortie, check=True)
    executer('nix-build', '<nixpkgs/nixos>', '-A', 'system', '-I', 'nixpkgs=' + nixpkgs,
        '-I', 'nixos-config=' + str(installe / 'configuration-interface.nix'),
        '--out-link', dossier / 'result', visible=True)
    candidat = str((dossier / 'result').resolve())
    exiger(candidat == b['systeme'], 'Construction différente de l’évaluation')
    racines = Path('/nix/var/nix/gcroots/vision-interface') / revision
    racines.mkdir(parents=True)
    for nom, cible in [('avant', avant['actif']), ('candidat', candidat), ('nixpkgs', nixpkgs), ('python', sys.executable)]:
        (racines / nom).symlink_to(cible)
    nginx = shlex.split(b['nginx'])
    executer(nginx[0], '-t', '-c', nginx[nginx.index('-c') + 1], visible=True)
    simulation = subprocess.run([str(Path(candidat) / 'bin/switch-to-configuration'), 'dry-activate'],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=True).stdout
    (dossier / 'simulation.txt').write_text(simulation)
    print(simulation, flush=True)
    publication = Path('/srv/vision-interface/releases') / manifeste['revisionApplication']
    publication.parent.mkdir(parents=True, exist_ok=True)
    exiger(not publication.exists(), 'Publication existante à vérifier séparément')
    shutil.copytree(installe / 'vendor/vision-interface', publication)
    for p in [publication.parent.parent, publication.parent, publication, *publication.rglob('*')]:
        p.chmod(0o755 if p.is_dir() else 0o644)
    verifier_artefact(publication)
    temoin = dossier / 'timer-verifie'
    executer('systemd-run', '--unit=vision-interface-timer-test-' + revision[:12],
        '--on-active=2s', '--timer-property=AccuracySec=1s',
        '/run/current-system/sw/bin/touch', temoin)
    for _ in range(15):
        if temoin.exists():
            break
        time.sleep(1)
    exiger(temoin.exists(), 'Le déclenchement systemd indépendant n’a pas été confirmé')
    exiger(etat() == avant, 'Le VPS a changé pendant la préparation')
    services()
    enregistrer(dossier / 'prepare.json', {'revision': revision, 'avant': avant,
        'candidat': candidat, 'configuration': str(installe / 'configuration-interface.nix'),
        'publication': str(publication), 'manifeste': manifeste, 'python': sys.executable})
    print('Préparation vérifiée ; aucun lien actif, service ou donnée modifié.', flush=True)


def lien(cible):
    temporaire = COURANT.with_name('suivant')
    temporaire.unlink(missing_ok=True)
    temporaire.symlink_to(cible)
    os.replace(temporaire, COURANT)


def retour(revision):
    dossier = chemins(revision)
    r = json.loads((dossier / 'prepare.json').read_text())
    subprocess.run(['systemctl', 'stop', 'vision-interface-appliquer-' + revision[:12]], check=False)
    with (dossier / 'finaliser.lock').open('a') as verrou:
        fcntl.flock(verrou, fcntl.LOCK_EX)
        if (dossier / 'termine.json').exists():
            return
        exiger((dossier / 'demarrage-engage').exists(), 'Aucune activation de cette opération : aucun retour à exécuter')
        exiger(etat()['actif'] in (r['avant']['actif'], r['candidat']), 'Une autre génération est active : retour refusé')
        (dossier / 'retour-engage').touch()
        shutil.copy2(dossier / 'configuration-avant.nix', ENTREE)
        executer(Path(r['avant']['actif']) / 'bin/switch-to-configuration', 'test', visible=True)
        executer('nix-env', '--profile', '/nix/var/nix/profiles/system', '--set', r['avant']['demarrage'])
        executer(Path(r['avant']['demarrage']) / 'bin/switch-to-configuration', 'boot', visible=True)
        if r['avant']['interface']:
            lien(r['avant']['interface'])
        elif COURANT.is_symlink() and str(COURANT.resolve()) == r['publication']:
            COURANT.unlink()
        services()
        enregistrer(dossier / 'retour.json', {'retabli': True})


def appliquer(revision):
    dossier = chemins(revision)
    r = json.loads((dossier / 'prepare.json').read_text())
    verrous = []
    for nom in ('matheval', 'vision'):
        verrou = open('/srv/' + nom + '/deploy.lock', 'a')
        fcntl.flock(verrou, fcntl.LOCK_EX)
        verrous.append(verrou)
    with (dossier / 'finaliser.lock').open('a') as verrou:
        fcntl.flock(verrou, fcntl.LOCK_EX)
        exiger(etat() == r['avant'], 'État modifié depuis la préparation')
        exiger(not (dossier / 'retour-engage').exists(), 'Retour déjà engagé')
        verifier_artefact(Path(r['publication']))
        lien(r['publication'])
        executer(Path(r['candidat']) / 'bin/switch-to-configuration', 'test', visible=True)
        services()
        enregistrer(dossier / 'essai.json', {'actif': r['candidat']})


def demarrer(revision):
    dossier = chemins(revision)
    exiger(not any((dossier / n).exists() for n in ('essai.json', 'termine.json', 'retour-engage')), 'Opération déjà engagée')
    r = json.loads((dossier / 'prepare.json').read_text())
    exiger(etat() == r['avant'], 'Nouvel audit nécessaire : état modifié')
    script = dossier / 'source/scripts/vision-interface-deployer.py'
    (dossier / 'demarrage-engage').touch()
    executer('systemd-run', '--unit=vision-interface-retour-' + revision[:12], '--on-active=15m',
        '--timer-property=AccuracySec=1s', '--setenv=PATH=' + os.environ['PATH'], r['python'], script, 'retour', revision)
    executer('systemctl', 'is-active', 'vision-interface-retour-' + revision[:12] + '.timer')
    executer('systemd-run', '--wait', '--pipe', '--unit=vision-interface-appliquer-' + revision[:12],
        '--setenv=PATH=' + os.environ['PATH'], r['python'], script, 'appliquer', revision, visible=True)


def finaliser(revision):
    dossier = chemins(revision)
    r = json.loads((dossier / 'prepare.json').read_text())
    with (dossier / 'finaliser.lock').open('a') as verrou:
        fcntl.flock(verrou, fcntl.LOCK_EX)
        exiger((dossier / 'essai.json').exists() and not (dossier / 'retour-engage').exists(), 'Essai absent ou retour engagé')
        courant = etat()
        exiger(courant['actif'] == r['candidat'] and courant['interface'] == r['publication'], 'Version active différente')
        exiger(all(courant[n] == r['avant'][n] for n in ('vision', 'matheval', 'configuration', 'demarrage')), 'Un autre changement est intervenu')
        services()
        temporaire = ENTREE.with_suffix('.vision-interface-new')
        temporaire.write_text('{ imports = [ ' + r['configuration'] + ' ]; }\n')
        temporaire.chmod(0o644)
        os.replace(temporaire, ENTREE)
        executer('nix-env', '--profile', '/nix/var/nix/profiles/system', '--set', r['candidat'])
        executer(Path(r['candidat']) / 'bin/switch-to-configuration', 'boot', visible=True)
        exiger(etat()['demarrage'] == r['candidat'], 'Profil de démarrage différent')
        services()
        enregistrer(dossier / 'termine.json', {'revision': revision, 'etat': etat(), 'manifeste': r['manifeste']})
    executer('systemctl', 'stop', 'vision-interface-retour-' + revision[:12] + '.timer')


if __name__ == '__main__':
    exiger(os.geteuid() == 0, 'Exécution réservée au runner administratif sur le VPS')
    os.umask(0o077)
    {'preparer': preparer, 'demarrer': demarrer, 'appliquer': appliquer,
     'finaliser': finaliser, 'retour': retour}[sys.argv[1]](sys.argv[2])
