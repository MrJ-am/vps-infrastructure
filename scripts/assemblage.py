#!/usr/bin/env python3
"""Sources exactes, sélection conservative et reçus locaux non attestés.

Aucune publication n'est autorisée par un reçu local. Les tests de qualification
distants devront être rejoués par la CI tant qu'une attestation n'est pas disponible.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import re
import subprocess
import sys
import time

RACINE = Path(__file__).resolve().parents[1]
DEPOTS = {'vps': ('vps-infrastructure', 'main'), 'vision': ('vision', 'main'),
          'matheval': ('M-moire', 'master'), 'logique': ('apprendre-a-demontrer', 'main'),
          'style': ('style-mrjam', 'main'), 'signature': ('Signature', 'main')}


def empreinte(data):
    return hashlib.sha256(data).hexdigest()


def lire(chemin):
    return json.loads(Path(chemin).read_text())


def manifeste(racine=RACINE):
    m = lire(racine / 'assemblage/manifest.json')
    if m['format'] != 1 or set(m['sources']) != set(DEPOTS):
        raise ValueError('Périmètre du manifeste invalide')
    for cle, (depot, branche) in DEPOTS.items():
        s = m['sources'][cle]
        revision_valide = s['revision'] == 'self' if cle == 'vps' else bool(re.fullmatch(r'[a-f0-9]{40}', s['revision']))
        if s['depot'] != 'MrJ-am/' + depot or s['branche'] != branche or not revision_valide:
            raise ValueError('Source non autorisée ou non verrouillée : ' + cle)
    return m


def chemins_sources(racine=RACINE, atelier=None):
    base = Path(atelier) if atelier else racine.parent
    return {cle: racine if cle == 'vps' else base / depot for cle, (depot, _) in DEPOTS.items()}


def verifier_sources(chemins, m, exact=True):
    for cle, p in chemins.items():
        revision = subprocess.check_output(['git', '-C', str(p), 'rev-parse', 'HEAD'], text=True).strip()
        if exact and cle != 'vps' and revision != m['sources'][cle]['revision']:
            raise ValueError('Révision différente du manifeste : ' + cle)
        if exact and cle != 'vps' and subprocess.check_output(['git', '-C', str(p), 'status', '--porcelain']):
            raise ValueError('Source de publication modifiée : ' + cle)


def catalogue(racine=RACINE):
    c = lire(racine / 'assemblage/suites.json')
    for nom, suite in c.items():
        if not suite.get('entrees') or not suite.get('commandes') or suite['niveau'] not in range(1, 8):
            raise ValueError('Suite incomplète : ' + nom)
        for besoin in suite.get('dependances', []):
            if besoin not in c:
                raise ValueError('Dépendance de suite inconnue : ' + besoin)
    return c


def correspond(chemin, motifs):
    from fnmatch import fnmatchcase
    return any(fnmatchcase(chemin, motif) for motif in motifs)


def selection(changements, suites):
    """Les dépendances de suites propagent l'impact aux consommateurs.
    Chemin inconnu : toutes les suites, sans présumer qu'il est éditorial.
    """
    choisis = set()
    for chemin in changements:
        if chemin == 'vps/assemblage/manifest.json':
            # Tant que les différences entre anciennes/nouvelles révisions des
            # composants ne sont pas disponibles, élargir plutôt que sous-tester.
            return sorted(suites)
        matches = {nom for nom, s in suites.items() if correspond(chemin, s['impact'])}
        if not matches:
            return sorted(suites)
        choisis.update(matches)
    while True:
        suivant = choisis | {nom for nom, s in suites.items() if choisis.intersection(s.get('dependances', []))}
        if suivant == choisis:
            return sorted(choisis)
        choisis = suivant


def changements_assemblage(avant, chemins):
    "Diff des révisions de bibliothèques ; inconnu/toolchain élargit sans fetch."
    if not re.fullmatch(r'[a-f0-9]{40}',avant or '') or set(avant)=={'0'}:
        return ['vps/assemblage/manifest.json']
    fichiers=subprocess.check_output(['git','diff','--name-only',avant,'HEAD'],cwd=chemins['vps'],text=True).splitlines()
    changes=['vps/'+p for p in fichiers if p!='assemblage/manifest.json']
    if 'assemblage/manifest.json' not in fichiers:return changes
    try:
        ancien=json.loads(subprocess.check_output(['git','show',avant+':assemblage/manifest.json'],cwd=chemins['vps']))
        actuel=manifeste(chemins['vps'])
        a=json.loads(json.dumps(ancien));b=json.loads(json.dumps(actuel))
        for nom in DEPOTS:
            a['sources'][nom]['revision']=b['sources'][nom]['revision']='comparee'
        if a!=b:return changes+['vps/assemblage/manifest.json']
        for nom in DEPOTS:
            if nom=='vps':continue
            precedent=ancien['sources'][nom]['revision'];suivant=actuel['sources'][nom]['revision']
            if precedent==suivant:continue
            if not re.fullmatch('[a-f0-9]{40}',precedent):raise ValueError('Ancienne révision inconnue')
            diff=subprocess.check_output(['git','diff','--name-only','-z',precedent,suivant],cwd=chemins[nom]).decode().split('\0')
            changes.extend(nom+'/'+p for p in diff if p)
    except (KeyError,ValueError,subprocess.CalledProcessError):
        return changes+['vps/assemblage/manifest.json']
    return changes or ['vps/assemblage/qualification-locale.json']


def entrees(suite, chemins):
    result = {}
    for cle, motifs in suite['entrees'].items():
        if cle not in DEPOTS:
            raise ValueError('Dépôt hors périmètre')
        for motif in motifs:
            files = sorted(p for p in chemins[cle].glob(motif) if p.is_file())
            if not files:
                raise ValueError('Entrée de suite absente : ' + cle + '/' + motif)
            for p in files:
                if p.is_symlink() or not p.resolve().is_relative_to(chemins[cle].resolve()):
                    raise ValueError('Entrée externe interdite')
                result[cle + '/' + str(p.relative_to(chemins[cle]))] = empreinte(p.read_bytes())
    return result


def compilation_entrees(chemins):
    "Sources du graphe métier, indépendantes des corrections de prose/tests."
    return entrees({'entrees': {
        'vps': ['mrjam-*.asd', 'lisp/**/*.lisp', 'assemblage/charger.lisp', 'assemblage/construire.lisp'],
        'vision': ['vision.asd', 'src/*.lisp'],
        'matheval': ['matheval.asd', 'lisp/*.lisp']}}, chemins)


def environnement(suite):
    versions = {}
    for nom, commande in suite.get('outils', {}).items():
        p = subprocess.run(commande, capture_output=True, text=True, check=True)
        binaire = shutil.which(commande[0])
        versions[nom] = {'version': p.stdout.strip(),
                         'executable_sha256': empreinte(Path(binaire).resolve().read_bytes())}
    # Seules configurations explicitement non secrètes ; ne jamais dumper env.
    valeurs = {k: os.environ.get(k, '') for k in suite.get('configuration', [])}
    if any(re.search('SECRET|TOKEN|PASSWORD|KEY|CREDENTIAL', k, re.I) for k in valeurs):
        raise ValueError('Configuration secrète interdite dans un reçu')
    natifs = {}
    motifs = ('/lib/*/libc.so.6', '/lib/*/libzstd.so.1', '/lib/*/libcrypto.so.3', '/lib/*/libpq.so.5', '/lib/*/libsqlite3.so.0') if 'sbcl' in versions or suite.get('candidat_metier') else ()
    for motif in motifs:
        for chemin in Path('/').glob(motif.lstrip('/')):
            natifs[str(chemin)] = empreinte(chemin.resolve().read_bytes())
    for cle in ('MRJAM_LIBCRYPTO', 'MRJAM_LIBPQ', 'MRJAM_LIBSQLITE'):
        chemin = os.environ.get(cle)
        if chemin:
            p = Path(chemin).resolve(strict=True)
            natifs[cle] = {'chemin': str(p), 'sha256': empreinte(p.read_bytes())}
    # SBCL_HOME est un chemin d'outillage, jamais un credential.
    sbcl_home = os.environ.get('SBCL_HOME')
    if sbcl_home and 'sbcl' in versions:
        runtime = Path(sbcl_home).parent.parent / 'bin/sbcl'
        if runtime.is_file():natifs['sbcl/runtime'] = empreinte(runtime.resolve().read_bytes())
        for chemin in sorted(Path(sbcl_home).rglob('*')):
            if chemin.is_file():
                natifs['sbcl/' + str(chemin.relative_to(sbcl_home))] = empreinte(chemin.read_bytes())
    return {'architecture': platform.machine(), 'systeme': platform.system(),
            'outils': versions, 'bibliotheques_natives': natifs,
            'os_sha256': empreinte(Path('/etc/os-release').read_bytes()), 'configuration': valeurs}


def identifiant_suite(nom, suite, chemins):
    result={'suite': nom, 'definition': empreinte(json.dumps(suite, sort_keys=True).encode()),
            'entrees': entrees(suite, chemins), 'environnement': environnement(suite)}
    if suite.get('candidat_frontend'):
        cle=suite['candidat_frontend']
        r=lire(RACINE/'state/frontends-candidats'/('dernier-'+cle+'.json'))
        p=RACINE/r['candidat']
        if p.is_symlink() or not p.resolve().is_relative_to(RACINE/'state/frontends-candidats'):
            raise ValueError('Candidat frontend extérieur')
        from frontends import contenus
        if contenus(p)!=r['fichiers']:raise ValueError('Candidat frontend modifié')
        result['candidat_frontend']={'fichiers':r['fichiers'],'revision':r['revision']}
    if suite.get('candidat_metier'):
        p=Path(os.environ.get('MRJAM_TEST_EXECUTABLE',RACINE/'state/artefacts/mrjam-metier'))
        r=lire(p.with_suffix('.qualification.json'))
        if empreinte(p.read_bytes())!=r['artefact_sha256'] or compilation_entrees(chemins)!=r['sources_lisp_sha256']:
            raise ValueError('Candidat métier différent des sources qualifiées')
        result['candidat_metier']={'sha256':r['artefact_sha256'],'sources':r['sources_lisp_sha256'],'compilation':r['compilation']}
    profiles={}
    for cle in suite.get('python_profils',[]):
        venv=RACINE/'state/outils-python'/cle
        python=venv/'bin/python'
        # RECORD décrit les modules effectivement installés, pas seulement pip
        # ou la phrase d'un agent. Aucun credential ni environnement complet.
        commande="import importlib.metadata as m,json,hashlib;print(json.dumps({d.metadata['Name']:{'version':d.version,'fichiers':{str(f):hashlib.sha256(d.locate_file(f).read_bytes()).hexdigest() for f in d.files or [] if d.locate_file(f).is_file()}} for d in m.distributions()},sort_keys=True))"
        modules=subprocess.check_output([python,'-c',commande])
        versions={re.sub(r'[-_.]+','-',n).lower():v['version'] for n,v in json.loads(modules).items()}
        attendus=lire(RACINE/'assemblage/dependances.json')['python_profils'][cle]['paquets']
        if any(versions.get(re.sub(r'[-_.]+','-',v['nom']).lower())!=v['version'] for v in attendus):
            raise ValueError('Versions Python différentes du profil verrouillé : '+cle)
        profiles[cle]={'python_sha256':empreinte(python.resolve().read_bytes()),
                       'paquets_sha256':empreinte(modules)}
    if profiles:result['python_profils']=profiles
    return result


def reutilisable(recu, identite):
    return (recu.get('format') == 1 and recu.get('resultat') == 'succes'
            and recu.get('identite') == identite and recu.get('confiance') == 'locale-non-attestee')


def executer(nom, suite, chemins, dossier, reference=False, ci=False):
    identite = identifiant_suite(nom, suite, chemins)
    recu_path = dossier / (nom + '.json')
    if not reference and not ci and recu_path.exists() and reutilisable(lire(recu_path), identite):
        print(json.dumps({'suite': nom, 'reutilise': True, 'confiance': 'locale-non-attestee'}))
        return True
    debut = time.monotonic()
    ok = True
    codes = []
    for commande in suite['commandes']:
        p = subprocess.run(commande, cwd=chemins[suite['repertoire']])
        codes.append(p.returncode)
        if p.returncode:
            ok = False
            break  # pas de retry en boucle jusqu'au vert
    # Refuse un résultat si le code/outil a changé pendant l'exécution.
    if identifiant_suite(nom, suite, chemins) != identite:
        raise ValueError('Entrées modifiées pendant la qualification : ' + nom)
    recu = {'format': 1, 'identite': identite, 'confiance': 'locale-non-attestee',
            'autorise_publication': False, 'resultat': 'succes' if ok else 'echec',
            'codes': codes, 'duree_secondes': round(time.monotonic() - debut, 4)}
    dossier.mkdir(parents=True, exist_ok=True)
    temporaire = recu_path.with_suffix('.json.tmp')
    temporaire.write_text(json.dumps(recu, ensure_ascii=False, indent=2) + '\n')
    temporaire.replace(recu_path)
    print(json.dumps({'suite': nom, 'reutilise': False, 'resultat': recu['resultat'], 'duree_secondes': recu['duree_secondes']}))
    return ok


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('operation', choices=['verifier', 'selection', 'tester'])
    p.add_argument('--atelier')
    p.add_argument('--changement', action='append', default=[])
    p.add_argument('--suite', action='append', default=[])
    p.add_argument('--reference', action='store_true', help='Toutes suites sans réutilisation')
    p.add_argument('--ci', action='store_true', help='Ne jamais croire un reçu local')
    p.add_argument('--exact', action='store_true', help='Sources propres au commit manifesté')
    args = p.parse_args()
    m, suites = manifeste(), catalogue()
    chemins = chemins_sources(atelier=args.atelier)
    if args.operation == 'verifier':
        verifier_sources(chemins, m, args.exact)
        print('Manifeste : six sources autorisées et catalogue valides.')
        return
    choisis = sorted(suites) if args.reference else args.suite or selection(args.changement, suites)
    if any(n not in suites for n in choisis):
        raise ValueError('Suite inconnue')
    if args.operation == 'selection':
        print(json.dumps({'suites': choisis, 'evitees': len(suites) - len(choisis)}))
        return
    if not choisis:
        raise ValueError('Aucune suite demandée')
    verifier_sources(chemins, m, args.exact)
    resultats = [executer(n, suites[n], chemins, RACINE / 'state/recus', args.reference, args.ci) for n in choisis]
    if not all(resultats):
        sys.exit(1)


if __name__ == '__main__':
    main()
