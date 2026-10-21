"""Renommage natif du seul propriétaire existant ; aucun alias de connexion.

API officielle PATCH/person, sauvegarde chiffrée/restauration isolée avant
mutation. Retour éventuel du seul attribut name, jamais d'une ancienne base.
"""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import tempfile
import types

PHASE = 'preconditions'


def exiger(ok, code):
    if not ok:
        raise ValueError(code)


def commande(args, **kwargs):
    r = subprocess.run(list(map(str, args)), capture_output=True, timeout=120, **kwargs)
    exiger(r.returncode == 0, 'commande_refusee')
    return r.stdout


def projection(api, sujet, token):
    attrs = api.http('/v1/person/' + sujet, token=token)['attrs']
    exiger(attrs.get('uuid') == [sujet], 'sujet_different')
    return {
        'attrs': {k: v for k, v in attrs.items()
                  if k not in ('name', 'spn', 'last_modified_cid')},
        'credentials': api.http('/v1/person/' + sujet + '/_credential/_status', token=token),
        'sessions': api.http('/v1/account/' + sujet + '/_user_auth_token', token=token),
    }, attrs


def renommer(api, sujet, ancien, nouveau, token):
    """Modifier seulement name ; l'UUID reste le sujet OAuth, jamais un alias."""
    exiger(isinstance(nouveau, str) and re.fullmatch('[A-Za-z][A-Za-z0-9_.-]{1,63}', nouveau),
           'nouveau_nom_invalide')
    nouveau = nouveau.lower()
    avant, attrs = projection(api, sujet, token)
    exiger(attrs.get('name') in ([ancien], [nouveau]), 'nom_concurrent')
    if attrs['name'] == [nouveau]:
        return {'deja_renomme': True, 'uuid_et_credentials_sessions_preserves': True}
    # Un conflit est refusé avant l'écriture. Le contrôle d'unicité natif
    # protège aussi contre une collision concurrente ou un service_account.
    exiger(api.http('/v1/person/' + nouveau, token=token) is None, 'nom_occupe')
    try:
        api.http('/v1/person/' + sujet, {'attrs': {'name': [nouveau]}}, token=token, method='PATCH')
        apres, attrs = projection(api, sujet, token)
        exiger(attrs.get('name') == [nouveau] and attrs.get('spn') == [nouveau + '@log.mrj.am'],
               'nom_natif_non_modifie')
        exiger(avant == apres, 'invariants_identite_modifies')
        exiger(api.http('/v1/person/' + nouveau, token=token)['attrs']['uuid'] == [sujet],
               'nouveau_nom_autre_sujet')
        # L'ancien nom n'est plus un identifiant natif. Aucun routage ajouté.
        exiger(api.http('/v1/person/' + ancien, token=token) is None, 'ancien_nom_encore_actif')
        return {'deja_renomme': False, 'uuid_et_credentials_sessions_preserves': True,
                'ancien_nom_retire': True, 'nom_et_spn_natifs_modifies': True}
    except Exception:
        # Timeout ambigu : relire l'état avant tout retour ciblé.
        actuel = api.http('/v1/person/' + sujet, token=token)['attrs']
        exiger(actuel.get('uuid') == [sujet], 'retour_sujet_different')
        if actuel.get('name') == [nouveau]:
            api.http('/v1/person/' + sujet, {'attrs': {'name': [ancien]}}, token=token, method='PATCH')
            verifie, nom = projection(api, sujet, token)
            exiger(nom.get('name') == [ancien] and verifie == avant, 'retour_nom_non_confirme')
        raise


def principal(base, sujet):
    with sqlite3.connect(base.resolve().as_uri() + '?mode=ro', uri=True, timeout=3) as db:
        db.execute('PRAGMA query_only=ON')
        return db.execute('SELECT subject,mail,duration,minimum,qualified_after FROM log_principaux WHERE subject=?',
                          (sujet,)).fetchall()


def pids():
    return {n: commande(['systemctl', 'show', n, '-p', 'MainPID', '--value']).strip()
            for n in ('kanidm', 'mrjam-metier', 'nginx', 'postgresql', 'sshd', 'forgejo', 'phpfpm-nextcloud')}


def main(revision, run, nouveau, source):
    global PHASE
    exiger(os.geteuid() == 0 and re.fullmatch('[a-f0-9]{40}', revision)
           and re.fullmatch('[0-9]{1,20}', run), 'contexte_invalide')
    os.umask(0o077)
    native = types.ModuleType('operateur_native_prive')
    exec(compile(source, '<operateur-native-verrouille>', 'exec'), native.__dict__)
    d = Path('/root/mrjam-assemblages') / revision
    plan_path = d / 'activation-log-privee.json'
    original = plan_path.read_bytes()
    plan = json.loads(original)
    sujet, ancien = plan['subject'], plan['name']
    base = Path('/var/lib/mrjam-metier/log/sessions.sqlite')
    lien = principal(base, sujet)
    exiger(len(lien) == 1 and lien[0][1] == plan['mail'].lower(), 'principal_different')
    proteges = pids()
    expr = '''let e=import <nixpkgs/nixos/lib/eval-config.nix> {modules=[/etc/nixos/configuration.nix];}; c=e.config; in {
      kanidm=toString c.services.kanidm.package;
      curl=toString e.pkgs.curl;
      recipient=c.services.vision.backupRecipient;
    }'''
    config = json.loads(commande(['nix-instantiate', '--eval', '--strict', '--json', '--expr', expr]))
    api = native.KanidmPrive(config['kanidm'], '/etc/kanidm/server.toml', config['curl'] + '/bin/curl')
    dest = Path('/var/backup/mrjam-log-identifiant')
    dest.mkdir(mode=0o700, exist_ok=True)
    PHASE = 'sauvegarde_restauration'
    with tempfile.TemporaryDirectory(prefix='log-identifiant-', dir=dest) as tmp:
        tmp = Path(tmp)
        backup = tmp / 'native.json.gz'
        api.commande('scripting', 'backup', str(backup))
        contenu = backup.read_bytes()
        exiger(0 < len(contenu) < 128 * 1024 * 1024, 'sauvegarde_hors_borne')
        ssh_public = commande(['ssh-keygen', '-y', '-f', '/etc/ssh/ssh_host_ed25519_key']).decode().strip()
        for nom, data in (('native', contenu), ('plan', original)):
            chiffre = commande(['age', '-r', ssh_public, '-r', config['recipient']], input=data)
            archive = dest / (run + '-' + nom + '.age')
            with archive.open('xb') as f:
                f.write(chiffre)
            clair = commande(['age', '-d', '-i', '/etc/ssh/ssh_host_ed25519_key', archive])
            exiger(hashlib.sha256(data).digest() == hashlib.sha256(clair).digest(), 'sauvegarde_non_recuperable')
        api.restaurer_verifier(backup, tmp / 'restauration', sujet)
        PHASE = 'renommage_natif'
        token = None
        try:
            token = api.login('idm_admin', api.recuperer('idm_admin'), tmp)
            resultat = renommer(api, sujet, ancien, nouveau, token)
            PHASE = 'synchronisation_plan'
            exiger(plan_path.read_bytes() == original and principal(base, sujet) == lien and pids() == proteges,
                   'plan_ou_principal_concurrent')
            plan['name'] = nouveau.lower()
            temp = plan_path.with_name('activation-log-privee.json.nouveau-nom')
            with temp.open('x') as f:
                json.dump(plan, f, ensure_ascii=False, indent=2)
                f.write('\n'); f.flush(); os.fsync(f.fileno())
            temp.replace(plan_path)
            fd = os.open(plan_path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        except Exception:
            if token and plan_path.read_bytes() == original:
                actuel = api.http('/v1/person/' + sujet, token=token)['attrs']
                if actuel.get('uuid') == [sujet] and actuel.get('name') == [nouveau.lower()]:
                    # Retour du seul nom, y compris si l'écriture du plan échoue.
                    renommer(api, sujet, nouveau.lower(), ancien, token)
            raise
        finally:
            api.commande('disable-account', 'idm_admin')
    PHASE = 'verification'
    exiger(pids() == proteges and principal(base, sujet) == lien, 'processus_ou_principal_modifie')
    resultat.update(sauvegarde_chiffree_recuperable=True, restauration_isolee=True,
                    principal_et_processus_preserves=True, aucun_alias=True,
                    plan_exploitation_synchronise=True, administrateur_technique_desactive=True)
    print(json.dumps(resultat))


if __name__ == '__main__':
    try:
        with open('/root/mrjam-log.lock', 'a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            main(sys.argv[1], sys.argv[2], NOUVEAU_NOM, NATIVE_SOURCE)
    except Exception:
        print(json.dumps({'renommage_confirme': False, 'phase': PHASE,
                          'diagnostic': 'aucune_valeur_personnelle_publiee'}), file=sys.stderr)
        sys.exit(1)
