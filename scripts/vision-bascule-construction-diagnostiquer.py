"""Lire uniquement le refus de construction 0856, avec projection fermée."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
REFUS = '0856c8a0e7466f7aa2dc6d6f44e432306542cdcf'
DOSSIER = Path('/root/vision-bascule-preparations')/REFUS
EMPREINTES = {
    'vision-bascule-preparer.py': '9370cc7e71a7f0b0f0b78b1d4cfda1bb373c4744a77ee218ab776a522421c8b2',
    'vision-bascule-composants.nix': '2e301033b4c4490f5ca72cc097c301eed2b67d11b54a4b5c31146d701bcba90f',
    'vision-configuration-reparer.py': '4901653327a64a5b8af9bff5bb1746f70107fde52495851dd0886e0cf1ac0c45',
}
MOTIFS = {
    'archive_non_reconnue': r'do not know how to unpack source archive',
    'archive_copie_refusee': r'cp: cannot stat|cannot copy|cannot access',
    'constructeur_echec': r'builder for .* failed|Cannot build .* Reason:',
    'dependance_echec': r'dependencies of derivation .* failed|[0-9]+ dependencies failed',
    'reseau': r'could not resolve|Could not resolve|Could not connect|failed to download|HTTP error',
    'disque_plein': r'No space left on device',
    'processus_tue': r'Killed|killed by signal|exit code 137',
    'lisp_compilation': r'COMPILE-FILE-ERROR|fatal ERROR|unhandled .* in --disable-debugger',
    'copie_source_hors_store': r'do not know how to unpack source archive /root/vision-bascule-preparations/[a-f0-9]{40}/vision',
}
NOMS = ('vision-bootstrap', 'vision-bascule-composants', 'mrjam-keycloak', 'keycloak',
    'mrj-auth-source', 'vision-cycle-source', 'mrjam-admission-source', 'mrjam-fermeture-source')


def charger(nom, chemin):
    s = importlib.util.spec_from_file_location(nom, chemin)
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


def classer(texte):
    # Ne jamais exporter de chemin, nom de dérivation libre ou ligne de journal.
    texte = re.sub(r'\x1b\[[0-9;]*m', '', texte)
    echecs = re.findall(r"(?:builder for |Cannot build )['\"]?(/nix/store/[a-z0-9]{32}-[^\s'\"]+\.drv)", texte)
    return dict(categories=sorted(n for n,m in MOTIFS.items() if re.search(m,texte)),
        composants=sorted(n for n in NOMS if any(re.fullmatch(
            r'/nix/store/[a-z0-9]{32}-'+re.escape(n)+r'(?:-[0-9.]+)?\.drv', p) for p in echecs)))


def main(revision):
    if os.geteuid() != 0 or not re.fullmatch('[a-f0-9]{40}',revision): raise ValueError()
    d = Path('/root/vision-bascule-diagnostics')/revision
    if ROOT != d/'source': raise ValueError()
    os.umask(0o077)
    prive = charger('prive_construction_bascule', ROOT/'scripts/identite-preparer.py')
    construction = charger('construction_bascule', ROOT/'scripts/vision-identite-construire.py')
    lecteur = charger('cadres_construction_bascule', ROOT/'scripts/vision-bascule-diagnostiquer.py')
    for p in (d.parent,d,ROOT,DOSSIER.parent,DOSSIER,DOSSIER/'source',DOSSIER/'source/scripts'):
        construction.dossier_prive(p)
    def lire(p,nom,maximum=65536):
        fd = os.open(p,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try: return prive.lire(fd,nom,maximum)
        finally: os.close(fd)
    sources = {n:lire(DOSSIER/'source/scripts',n) for n in EMPREINTES}
    if any(hashlib.sha256(sources[n].encode()).hexdigest() != h for n,h in EMPREINTES.items()): raise ValueError()
    trace = lire(DOSSIER,'diagnostic-prive.log',262144)
    cadres = lecteur.classer(trace,sources,DOSSIER)
    if not any(c['fichier']=='vision-bascule-preparer.py' and c['fonction']=='preparer' and c['ligne']==241 for c in cadres['cadres']): raise ValueError()
    evaluation = json.loads(lire(DOSSIER,'evaluation-privee.json'))
    if not (evaluation['garde_activation'] is True and evaluation['generation_constructible'] is False and
            evaluation['activation'] is False and evaluation['inscriptions'] is False): raise ValueError()
    if (DOSSIER/'preparation.json').exists() or (Path('/var/lib/postgresql')/('vision-bascule-'+REFUS[:12])).exists(): raise ValueError()
    rapport = dict(version=1,infrastructure=revision,refus=REFUS,sources_exactes=True,
        cadres=cadres['cadres'],exceptions=cadres['exceptions'],categories_nix=cadres['categories'],
        construction=classer(trace),evaluation_composants_reussie=True,garde_activation=True,
        cluster_isole_present=False,preparation_achevee=False,production_modifiee=False,activation=False,inscriptions=False)
    print(json.dumps(rapport),flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('revision'); a = p.parse_args()
    try: main(a.revision)
    except Exception:
        print(json.dumps(dict(diagnostic_construction_refuse=True,production_modifiee=False)),flush=True)
        raise SystemExit(1)
