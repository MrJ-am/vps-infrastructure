"""Préparer la bascule Log depuis le même bundle qualifié ; aucune activation."""
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True

def module(nom, fichier):
    spec = importlib.util.spec_from_file_location(nom, ROOT/'scripts'/fichier)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

s = module('log_stage_verifier', 'monolithe-preparer.py')

def preparer(revision):
    s.exiger(os.geteuid() == 0 and re.fullmatch('[a-f0-9]{40}', revision), 'Opérateur/révision refusés')
    os.umask(0o077)
    d = Path('/root/mrjam-assemblages')/revision
    cert = s.verifier_bundle(d/'payload')
    s.exiger(cert['revision'] == revision and 'kanidm' in cert['qualification']['sorties_nix'], 'Bundle Log incomplet')
    avant = s.etat(d)
    s.exiger(avant['generation'] == avant['demarrage'], 'Génération de départ non enregistrée')
    if (d/'preparation-log.json').exists():
        p = json.loads((d/'preparation-log.json').read_text())
        s.exiger(p['avant'] == avant, 'État différent depuis préparation Log')
        print(json.dumps({'preparation_log': 'deja_effectuee', 'activation': False})); return
    s.commande(['systemctl','is-active',*s.TIERS,'nginx','postgresql','mrjam-metier'],d)
    s.exiger(shutil.disk_usage('/').free > 3*1024**3, 'Espace de transition insuffisant')
    public = s.PUBLICATION_ROOT/revision
    if not public.exists():
        public.mkdir(parents=True,mode=0o755)
        for nom in cert['frontends']: shutil.copytree(d/'payload/frontends'/nom,public/nom)
    s.permissions_ressources(public)
    bank = json.loads((d/'payload/matheval/research/bank.json').read_text())
    params = dict(configuration=avant['configuration_cible'], paquet=cert['qualification']['sorties_nix']['metier'],
                  documentVision=str(public/'vision'), ressourcesMatheval=str(public/'matheval'),
                  bankVersion=bank['version'], kanidm=cert['qualification']['sorties_nix']['kanidm'])
    expr = '(import '+str(ROOT/'scripts/log-evaluation.nix')+' { '+''.join(k+'='+json.dumps(v)+'; ' for k,v in params.items())+'})'
    r = json.loads(s.commande(['nix-instantiate','-I','nixpkgs='+s.NIXPKGS,'--eval','--strict','--json','--expr',expr+'.rapport'],d))
    (d/'evaluation-log-privee.json').write_text(json.dumps(r,indent=2)+'\n')
    s.exiger(r['avant'] == avant['generation'] and r['assertions'], 'Évaluation active ou assertions différentes')
    s.exiger(r['protegeAvant'] == r['protegeAmorcage'] == r['protegeApres'], 'Un service préservé changerait')
    s.exiger(r['postgresAccesAvant']['authentication'] == r['postgresAccesApres']['authentication'], 'HBA changé hors périmètre')
    def lignes(v): return [x.strip() for x in v.splitlines() if x.strip() and not x.lstrip().startswith('#')]
    s.exiger(lignes(r['postgresAccesApres']['identMap']) == lignes(r['postgresAccesAvant']['identMap'])+
             ['mrj_identite mrjam-metier vision_identite'], 'Mapping peer différent')
    sources = {}
    racines = Path('/nix/var/nix/gcroots/mrjam-log')/revision; racines.mkdir(parents=True,exist_ok=True)
    for nom, attribut in [('amorcage','moduleAmorcage'),('candidat','moduleLog')]:
        p = d/('configuration-log-'+nom+'.nix')
        p.write_text('{ imports = [ '+json.dumps(avant['configuration_cible'])+' '+expr+'.'+attribut+' ]; }\n')
        construit = s.commande(['nix-build','<nixpkgs/nixos>','-A','system','-I','nixpkgs='+s.NIXPKGS,
                    '-I','nixos-config='+str(p),'--out-link',racines/nom,'--max-jobs','1','--cores','2'],d).decode().strip()
        s.exiger(construit == r['amorcage' if nom == 'amorcage' else 'apres'], 'Construction différente')
        sources[nom] = str(p)
    # Vérifier réellement le Nginx généré avant toute bascule/identité.
    nginx=re.findall(r'/nix/store/[a-z0-9]{32}-[^/\s"\']+/bin/nginx',r['nginx'])
    configs=re.findall(r'/nix/store/[a-z0-9]{32}-[^/\s"\']+\.conf',r['nginx'])
    s.exiger(len(nginx)==len(configs)==1,'Configuration Nginx candidate ambiguë')
    s.commande([nginx[0],'-t','-c',configs[0]],d)
    s.exiger(s.etat(d) == avant, 'Activation concurrente')
    p = dict(format=1, revision=revision, avant=avant, candidat=r['apres'], amorcage=r['amorcage'],
             configurations=sources, parametres=params, artefact_sha256=cert['qualification']['artefact_sha256'],
             inscriptions_preservees=True, activation=False)
    (d/'preparation-log.json').write_text(json.dumps(p,indent=2)+'\n')
    # Le restaurateur déjà qualifié reste le propriétaire de la sauvegarde et
    # des contrôles des bases métier, pas une nouvelle implémentation parallèle.
    (d/'preparation.json').write_text(json.dumps(dict(p,parametres=params),indent=2)+'\n')
    (d/'evaluation-privee.json').write_text(json.dumps({'postgres':r['protegeAvant']['postgres']['package']},indent=2)+'\n')
    print(json.dumps({k:p[k] for k in ('revision','candidat','amorcage','activation','inscriptions_preservees')}))

if __name__ == '__main__':
    try:
        with open('/root/mrjam-log.lock','a') as f:
            fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB); preparer(sys.argv[1])
    except Exception as e:
        if len(sys.argv)==2 and re.fullmatch('[a-f0-9]{40}',sys.argv[1]):
            d=Path('/root/mrjam-assemblages')/sys.argv[1]
            if d.is_dir(): (d/'erreur-log-preparation-privee.log').write_text(traceback.format_exc())
        print(json.dumps({'preparation_log':'refusee','exception':type(e).__name__,
            'regle':str(e) if type(e) is ValueError else 'Diagnostic privé requis'}),file=sys.stderr); sys.exit(1)
