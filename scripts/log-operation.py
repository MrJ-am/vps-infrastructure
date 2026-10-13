"""Promotion Log fermée dans la CI centrale ; aucun test de développement distant."""
import importlib.util
import os
from pathlib import Path
import shlex
import subprocess
import hashlib
import json


def correction_connexion():
    """Entrées exactes des contrôles locaux ; aucune réexécution de tests en CI.

    Comme le scellement existant, provenance propriétaire + dépôt privé main,
    reçus explicitement non attestés. Aucun cache extérieur n'autorise ce chemin.
    """
    from assemblage import catalogue, entrees
    p=json.loads((ROOT/'operations/log-connexion-candidat.json').read_text())
    stage.exiger(p['format']==1 and p['origine_preuves']=='codex-local-non-attestee'
                 and p['soumission_autorisee_par_proprietaire'] is True, 'Correction non qualifiée')
    stage.exiger(__import__('re').fullmatch('[a-f0-9]{40}',p['revision_sources']), 'Révision correction invalide')
    noms=('log-routage-nix','log-connexion')
    stage.exiger(set(p['recus'])==set(noms), 'Contrôles de correction incomplets')
    suites=catalogue()
    for nom in noms:
        r=p['recus'][nom]; suite=suites[nom]
        stage.exiger(r['format']==1 and r['resultat']=='succes' and r['confiance']=='locale-non-attestee'
                     and r['autorise_publication'] is False and len(r['codes'])==len(suite['commandes'])
                     and all(c==0 for c in r['codes']), 'Contrôle local refusé')
        stage.exiger(r['identite']['definition']==hashlib.sha256(json.dumps(suite,sort_keys=True).encode()).hexdigest()
                     and r['identite']['entrees']==entrees(suite,{'vps':ROOT}), 'Entrées différentes de la qualification')
    noms_sources=('modules/log-referrer.nix','scripts/log-connexion-evaluation.nix','scripts/log-connexion-promouvoir.py')
    sources={nom:(ROOT/nom).read_text() for nom in noms_sources}
    stage.exiger(set(p['empreintes'])==set(noms_sources), 'Périmètre correction différent')
    for nom,source in sources.items():
        stage.exiger(hashlib.sha256(source.encode()).hexdigest()==p['empreintes'][nom], 'Source de correction différente')
        qualifie=subprocess.check_output(['git','show',p['revision_sources']+':'+nom],cwd=ROOT)
        stage.exiger(qualifie==source.encode(), 'Révision de qualification différente')
    d=stage.descriptor('log')
    stage.exiger(p['revision_assemblage']==d['revision_operateurs'] and p['artefact_sha256']==d['artefact_sha256'],
                 'Assemblage actif attendu différent')
    payload={k:p[k] for k in ('format','revision_sources','revision_assemblage','generation_attendue','artefact_sha256','empreintes')}
    payload['sources']=sources
    code="import json\nnamespace={'__name__':'correction_connexion_ci'}\nexec("+repr(sources['scripts/log-connexion-promouvoir.py'])+",namespace)\n"
    code+="import fcntl\nwith open('/root/mrjam-log.lock','a') as lock:\n fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)\n namespace['promouvoir'](json.loads("+repr(json.dumps(payload))+"))\n"
    stage.ssh('nix-shell -I nixpkgs='+stage.manifeste()['toolchain']['production']['nixpkgs']+
              ' -p python3 --run '+shlex.quote('python3 -B -'),input=code.encode())


def restaurer_clients_mcp():
    """Même circuit de provenance locale, opération limitée aux clients publics."""
    from assemblage import catalogue, entrees
    p=json.loads((ROOT/'operations/log-clients-mcp.json').read_text())
    stage.exiger(__import__('re').fullmatch('[a-f0-9]{40}',p['revision_sources']), 'Révision MCP invalide')
    suite=catalogue()['log-parcours'];r=p['recu']
    stage.exiger(p['format']==1 and p['origine_preuves']=='codex-local-non-attestee'
                 and r['format']==1 and r['resultat']=='succes' and r['confiance']=='locale-non-attestee'
                 and r['autorise_publication'] is False and len(r['codes'])==len(suite['commandes'])
                 and all(c==0 for c in r['codes']),'Reprise MCP non qualifiée')
    stage.exiger(r['identite']['entrees']==entrees(suite,{'vps':ROOT})
                 and r['identite']['definition']==hashlib.sha256(json.dumps(suite,sort_keys=True).encode()).hexdigest(),
                 'Entrées MCP différentes de la qualification')
    source=(ROOT/'scripts/log-clients-mcp.py').read_bytes()
    stage.exiger(hashlib.sha256(source).hexdigest()==p['operateur_sha256'],'Opérateur MCP différent')
    stage.exiger(subprocess.check_output(['git','show',p['revision_sources']+':scripts/log-clients-mcp.py'],cwd=ROOT)==source,
                 'Révision opérateur MCP différente')
    # Aucun shell libre et aucune modification de l'IdP/artefact/génération.
    stage.ssh('nix-shell -I nixpkgs='+stage.manifeste()['toolchain']['production']['nixpkgs']+
              ' -p python3 --run '+shlex.quote('python3 -B -'),input=source)

ROOT=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('stage_log',ROOT/'scripts/monolithe-stage.py')
stage=importlib.util.module_from_spec(s);s.loader.exec_module(stage)

def main():
    stage.exiger(os.environ.get('GITHUB_ACTIONS')=='true' and os.environ.get('GITHUB_REF')=='refs/heads/main',
                 'Opérateur réservé à la CI centrale main')
    op=os.environ.get('MRJAM_OPERATION')
    stage.exiger(op in ('preparer','deployer','courriel','retour','diagnostic','corriger-connexion','restaurer-clients-mcp'),'Opération Log inconnue')
    if op=='restaurer-clients-mcp':
        restaurer_clients_mcp(); return
    if op=='corriger-connexion':
        correction_connexion(); return
    if op in ('preparer','deployer'): stage.main('log')
    if op=='preparer': return
    d=stage.descriptor('log');rev=d['revision_operateurs']
    root=Path('/root/mrjam-assemblages')/rev/'payload/vps/scripts'
    if op=='diagnostic':
        cmd='python3 - '+rev
        stage.ssh('nix-shell -I nixpkgs='+stage.manifeste()['toolchain']['production']['nixpkgs']+
                  ' -p python3 --run '+shlex.quote(cmd),input=(ROOT/'scripts/log-diagnostic.py').read_bytes())
        return
    commandes=[]
    if op=='deployer': commandes.append('python3 -B '+str(root/'monolithe-restaurer.py')+' '+rev+' --metier-actif')
    commandes.append('python3 -B '+str(root/'log-activer.py')+' '+{'deployer':'activer','retour':'retour','courriel':'courriel'}[op]+' '+rev)
    for cmd in commandes:
        stage.ssh('nix-shell -I nixpkgs='+stage.manifeste()['toolchain']['production']['nixpkgs']+
                  ' -p python3 --run '+shlex.quote(cmd))

if __name__=='__main__': main()
