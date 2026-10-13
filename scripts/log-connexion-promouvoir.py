"""Correction fermée des seuls en-têtes Log ; aucun accès aux comptes/bases.

Le même SBCL et le même Kanidm restent actifs. Retour de configuration vers
la génération Native précédente seulement, sans restauration de données.
"""
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path('/root/mrjam-corrections/log-connexion')
FICHIERS = ('modules/log-referrer.nix', 'scripts/log-connexion-evaluation.nix',
            'scripts/log-connexion-promouvoir.py')


def exiger(v, message):
    if not v: raise ValueError(message)


def verifier_evaluation(r, avant):
    exiger(r['avant'] == avant['generation'] == avant['demarrage'], 'Génération de départ différente')
    exiger(r['invariants'] and r['assertions'] and r['nativeActif'], 'Configuration hors périmètre')
    exiger('no-referrer' in r['extraAvant'] and 'strict-origin' in r['extraApres']
           and 'no-referrer' not in r['extraApres'], 'Politique Referrer inattendue')
    exiger(r['proxyApres'].split() == (r['proxyAvant']+'\nproxy_hide_header Referrer-Policy;').split(),
           'Autre changement du proxy natif')


def ecrire(p, v):
    tmp=p.with_name(p.name+'.nouveau')
    with tmp.open('w') as f:
        json.dump(v, f, indent=2); f.write('\n'); f.flush(); os.fsync(f.fileno())
    os.replace(tmp, p)


def charger_stage(revision):
    exiger(re.fullmatch('[a-f0-9]{40}', revision), 'Révision assemblage invalide')
    s=importlib.util.spec_from_file_location('connexion_stage',
      Path('/root/mrjam-assemblages')/revision/'payload/vps/scripts/monolithe-preparer.py')
    m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


def pids(stage, d):
    return {n:stage.commande(['systemctl','show',n,'-p','MainPID','--value'],d).decode().strip()
            for n in (*stage.TIERS, 'kanidm', 'mrjam-metier', 'postgresql')}


def configuration(cible):
    p=Path('/etc/nixos/configuration.nix'); tmp=p.with_name('configuration.nix.mrjam-candidat')
    exiger(not tmp.exists() and not tmp.is_symlink(), 'Configuration concurrente')
    tmp.symlink_to(cible); os.replace(tmp,p)


def retour(d, stage, plan):
    actuel=stage.etat(d)
    exiger(actuel['generation'] in (plan['avant']['generation'], plan['candidat']), 'Bascule concurrente')
    configuration(plan['avant']['configuration_lien'] or plan['avant']['configuration_cible'])
    stage.commande(['nix-env','-p','/nix/var/nix/profiles/system','--set',plan['avant']['generation']],d)
    stage.commande([plan['avant']['generation']+'/bin/switch-to-configuration','switch'],d)
    ecrire(d/'retour.json', {'configuration_seule':True,'identites_et_donnees_non_restaurees':True})


def promouvoir(payload):
    exiger(os.geteuid()==0 and payload['format']==1, 'Opérateur refusé')
    os.umask(0o077); sys.dont_write_bytecode=True
    revision=payload['revision_sources']
    exiger(re.fullmatch('[a-f0-9]{40}',revision), 'Révision correction invalide')
    exiger(set(payload['sources'])==set(FICHIERS), 'Sources de correction différentes')
    for nom, source in payload['sources'].items():
        exiger(hashlib.sha256(source.encode()).hexdigest()==payload['empreintes'][nom], 'Source non qualifiée')
    d=ROOT/revision
    exiger(not d.exists(), 'Correction déjà engagée : constater son issue avant toute répétition')
    stage=charger_stage(payload['revision_assemblage'])
    avant=stage.etat(Path('/root/mrjam-assemblages')/payload['revision_assemblage'])
    exiger(avant['generation']==payload['generation_attendue']==avant['demarrage'], 'Production différente')
    ROOT.mkdir(parents=True,exist_ok=True,mode=0o700)
    stage.commande(['systemctl','is-active','kanidm','mrjam-metier','postgresql','nginx'],ROOT)
    d.mkdir(parents=True,mode=0o700)
    for nom, source in payload['sources'].items(): (d/Path(nom).name).write_text(source)
    expr='import '+str(d/'log-connexion-evaluation.nix')+' { configuration='+json.dumps(avant['configuration_cible'])+'; correction='+json.dumps(str(d/'log-referrer.nix'))+'; }'
    r=json.loads(stage.commande(['nix-instantiate','-I','nixpkgs='+stage.NIXPKGS,
             '--eval','--strict','--json','--expr',expr],d))
    verifier_evaluation(r, avant)
    candidat=d/'configuration.nix'
    candidat.write_text('{ imports = [ '+json.dumps(avant['configuration_cible'])+' '+json.dumps(str(d/'log-referrer.nix'))+' ]; }\n')
    gcroot=Path('/nix/var/nix/gcroots/mrjam-log-connexion')/revision
    gcroot.parent.mkdir(parents=True,exist_ok=True)
    generation=stage.commande(['nix-build','<nixpkgs/nixos>','-A','system','-I','nixpkgs='+stage.NIXPKGS,
              '-I','nixos-config='+str(candidat),'--out-link',gcroot,'--max-jobs','1','--cores','2'],d).decode().strip()
    exiger(generation==r['apres'], 'Génération différente de l’évaluation')
    nginx=re.findall(r'/nix/store/[a-z0-9]{32}-[^/\s"\']+/bin/nginx',r['nginx'])
    configs=re.findall(r'/nix/store/[a-z0-9]{32}-[^/\s"\']+\.conf',r['nginx'])
    exiger(len(nginx)==len(configs)==1, 'Configuration Nginx ambiguë')
    stage.commande([nginx[0],'-t','-c',configs[0]],d)
    processus=pids(stage,d)
    exiger(stage.sha(Path('/proc')/processus['mrjam-metier']/'exe')==payload['artefact_sha256'], 'Artefact métier différent')
    exiger(stage.etat(d)==avant, 'Configuration concurrente')
    plan=dict(avant=avant,candidat=generation,revision_assemblage=payload['revision_assemblage'],pids=processus)
    ecrire(d/'plan.json',plan)
    timer='mrjam-log-connexion-retour-'+revision[:12]
    stage.commande(['systemd-run','--unit='+timer,'--on-active=5min',
       '/run/current-system/sw/bin/nix-shell','-I','nixpkgs='+stage.NIXPKGS,'-p','python3','--run',
       'python3 -B '+str(d/'log-connexion-promouvoir.py')+' retour '+revision],d)
    try:
        configuration(str(candidat))
        stage.commande(['nix-env','-p','/nix/var/nix/profiles/system','--set',generation],d)
        stage.commande([generation+'/bin/switch-to-configuration','switch'],d)
        exiger(stage.etat(d)['generation']==stage.etat(d)['demarrage']==generation, 'Activation non constatée')
        exiger(pids(stage,d)==processus, 'Un processus protégé a redémarré')
        stage.commande(['systemctl','is-active','kanidm','mrjam-metier','postgresql','nginx'],d)
        # Sonde anonyme réelle, ni identifiant ni POST de connexion personnel.
        import urllib.request
        with urllib.request.urlopen('https://log.mrj.am/ui/login',timeout=20) as response:
            exiger(response.status==200 and response.headers.get_all('Referrer-Policy')==['strict-origin'],
                    'En-tête réellement servi différent')
        stage.commande(['systemctl','stop',timer+'.timer'],d)
        preuve=dict(format=1,revision_sources=revision,generation=generation,
             artefact_sha256=payload['artefact_sha256'],processus_proteges_inchanges=True,
             referrer_policy='strict-origin',controle_origine_conserve=True,
             comptes_et_donnees_non_modifies=True,connexion_personnelle='a_verifier_par_utilisateur')
        ecrire(d/'termine.json',preuve); print(json.dumps(preuve))
    except Exception:
        retour(d,stage,plan)
        stage.commande(['systemctl','stop',timer+'.timer'],d)
        raise


if __name__=='__main__':
    with open('/root/mrjam-log.lock','a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if len(sys.argv)==3 and sys.argv[1]=='retour' and re.fullmatch('[a-f0-9]{40}',sys.argv[2]):
            d=ROOT/sys.argv[2]; plan=json.loads((d/'plan.json').read_text())
            if not (d/'termine.json').exists():retour(d,charger_stage(plan['revision_assemblage']),plan)
        else: raise ValueError('Opération fermée requise')
