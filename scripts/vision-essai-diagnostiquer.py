"""Lire uniquement la simulation privée qualifiée de1760809, sans nouvel essai."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]
REFUS='1760809584d4a9e59264cb8761bdb3d69aaef445'
HASHES={'vision-essai-qualification.py':'9194ffb03db0a2a74e812078d1e23d3e29a23a3bb31a7deae67006b83377f5d2',
    'vision-bascule-preparer.py':'a8232533a434f1914aa97a1458908498f61b3af774c4e9d6bbfb7fe559354cc3'}
CONNUS=frozenset(('sshd','nginx','nginx-config-reload','postgresql','postgresql-setup','matheval',
    'vision','vision-bootstrap','vision-migrate','vision-embeddings','mrj-auth','keycloak',
    'mrjam-amorcage-identite','mrjam-amorcage-postgresql','mrjam-amorcage-sauvegarde',
    'postgresqlBackup-vision','postgresqlBackup-matheval','vision-gestion','vision-cycle','vision-purge',
    'mrjam-admission','mrjam-fermeture','mrjam-courriel','mrjam-sauvegarde',
    'systemd-tmpfiles-resetup','systemd-journald','systemd-journald@identite','systemd-networkd',
    'systemd-journald-varlink@identite','systemd-sysctl','nix-daemon','acme-log.mrj.am'))


def exiger(c):
    if not c: raise ValueError('Diagnostic de simulation refusé')


def charger(nom,p):
    s=importlib.util.spec_from_file_location(nom,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m


def classer(texte):
    texte=re.sub(r'\x1b\[[0-9;]*[A-Za-z]','',texte)
    exiger(len(texte)<1048576)
    actions=[];inconnues=0
    for action,noms in re.findall(r'would (stop|restart|reload|start) the following units: ([^\n]+)',texte):
        for u in {u.strip() for u in noms.split(',')}:
            suffixe=next((s for s in ('.service','.timer','.socket') if u.endswith(s)),None)
            if suffixe and u[:-len(suffixe)] in CONNUS:actions.append(dict(action=action,unite=u))
            else:inconnues+=1
    return dict(activation_simulee='would activate the configuration' in texte,
        redemarrage_systemd_annonce=bool(re.search(r'would restart systemd',texte)),
        arret_swap_annonce=bool(re.search(r'would stop swap',texte)),
        actions_connues=sorted(actions,key=lambda a:(a['action'],a['unite']))[:64],unites_inconnues=inconnues)


def main(revision):
    exiger(os.geteuid()==0 and re.fullmatch('[a-f0-9]{40}',revision) and
        ROOT==Path('/root/vision-bascule-diagnostics')/revision/'source')
    construction=charger('construction_diagnostic_essai',ROOT/'scripts/vision-identite-construire.py')
    prive=charger('prive_diagnostic_essai',ROOT/'scripts/identite-preparer.py')
    d=Path('/root/vision-bascule-preparations')/REFUS
    for p in (ROOT.parent.parent,ROOT.parent,ROOT,d.parent,d,d/'source',d/'source/scripts'):
        construction.dossier_prive(p)
    def lire(p,n,maximum=1048576):
        fd=os.open(p,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:return prive.lire(fd,n,maximum)
        finally:os.close(fd)
    sources={n:lire(d/'source/scripts',n) for n in HASHES}
    exiger(all(hashlib.sha256(sources[n].encode()).hexdigest()==h for n,h in HASHES.items()))
    projection=charger('projection_diagnostic_essai',ROOT/'scripts/vision-bascule-diagnostiquer.py')
    trace=projection.classer(lire(d,'diagnostic-prive.log',262144),sources,d)
    exiger(dict(fichier='vision-essai-qualification.py',ligne=179,fonction='preparer') in trace['cadres'])
    exiger(not (d/'essai-preparation.json').exists() and not (d/'entree.nix').exists() and
        not (Path('/var/lib/postgresql')/('vision-bascule-'+REFUS[:12])).exists())
    association=charger('association_diagnostic_essai',ROOT/'scripts/vision-bascule-principaux.py')
    old=Path('/root/vision-proprietaire-operations')/association.OBSERVATION/'source'
    exiger(hashlib.sha256(lire(old/'scripts','vision-proprietaire-enroler.py')).hexdigest()==
        '61ba89f8551a95a026293fca6ff3e79a6e5a9b6ed34c96255aa9828986ec2c2e')
    observateur=charger('observateur_diagnostic_essai',old/'scripts/vision-proprietaire-enroler.py')
    observateur.main(association.OBSERVATION,observer=True,activation_seule=True)
    resultat=classer(lire(d,'dry-activate-prive.txt'))
    generation=str((d/'generation-essai').resolve(strict=True));construction.store(generation)
    exiger((Path(generation)/'bin/switch-to-configuration').is_file())
    def texte_unite(systeme):
        p=Path(systeme)/'etc/systemd/system/systemd-tmpfiles-resetup.service'
        reel=p.resolve(strict=True);exiger(str(reel).startswith('/nix/store/') and reel.stat().st_size<1048576)
        return re.sub(r'(?m)^X-Restart-Triggers=[^\n]*\n?','',reel.read_text())
    identique=texte_unite(str(Path('/run/current-system').resolve()))==texte_unite(generation)
    rapport=dict(version=1,infrastructure=revision,refus=REFUS,sources_exactes=True,
        generation_construite_presente=True,cluster_retire=True,socle_conserve=True,
        resetup_identique_hors_triggers=identique,**resultat,production_modifiee=False,activation=False,inscriptions=False)
    observateur.main(association.OBSERVATION,observer=True,activation_seule=True)
    print(json.dumps(rapport),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('revision');a=p.parse_args()
    try:main(a.revision)
    except Exception:
        print(json.dumps(dict(diagnostic_essai_refuse=True,production_modifiee=False,activation=False)),flush=True)
        raise SystemExit(1)
