"""Préparer un système Nix depuis le candidat local reçu, sans activation.

Le bundle est privé. Erreurs détaillées restent sur le VPS ; seuls agrégats et
révisions sont imprimés. Aucune migration SQL, tâche métier, IdP ou SMTP ici.
"""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import stat
import subprocess
import sys
import traceback

sys.dont_write_bytecode=True # Le bundle scellé reste immuable entre opérations.

NIXPKGS='/nix/store/81s59zcy998ym4b36ayr29cjc9yhma5n-nixos-26.05.8639.c5c4a43b0e80/nixos'
TIERS=('sshd','mrj-auth','keycloak','vision-embeddings','phpfpm-nextcloud',
       'redis-nextcloud','nextcloud-backup.timer','postgresqlBackup-vision.timer',
       'postgresqlBackup-matheval.timer')
ETATS={
 'cycle-courriels':'/var/lib/vision-cycle/courriels.sqlite',
 'admissions':'/var/lib/mrjam-admission/admissions.sqlite',
 'admission-courriels':'/var/lib/mrjam-admission/courriels.sqlite',
 'fermeture-courriels':'/var/lib/mrjam-fermeture/courriels.sqlite',
 'courriel':'/var/lib/mrjam-courriel/file.sqlite',
 'effacements':'/var/lib/vision-effacements/demandes.jsonl',
 'effacements-cycle':'/var/lib/vision-cycle/effacements.jsonl',
 'effacements-fermeture':'/var/lib/mrjam-fermeture/effacements.jsonl'}


def exiger(v,message):
    if not v:raise ValueError(message)


def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()


def commande(args,d,*,input=None,timeout=1800,rapport_complet=False):
    p=subprocess.run([str(a) for a in args],input=input,stdout=subprocess.PIPE,
                     stderr=subprocess.STDOUT if rapport_complet else subprocess.PIPE,timeout=timeout)
    if p.returncode:
        (d/'erreur-commande-privee.log').write_bytes(p.stdout if rapport_complet else p.stderr)
        raise RuntimeError('Commande refusée : '+Path(str(args[0])).name+', code '+str(p.returncode))
    return p.stdout


def verifier_bundle(root):
    cert=json.loads((root/'stage.json').read_text())
    exiger(cert['format']==2 and cert['activation'] is False
           and cert['origine_preuves']=='codex-local-non-attestee','Format de stage refusé')
    files={}
    for p in root.rglob('*'):
        s=p.lstat();exiger(stat.S_ISDIR(s.st_mode) or stat.S_ISREG(s.st_mode),'Fichier non régulier dans le bundle')
        if p.is_file() and p!=root/'stage.json':files[str(p.relative_to(root))]=sha(p)
    exiger(files==cert['fichiers'],'Empreintes de bundle différentes')
    exiger(cert['manifest']['toolchain']['production']['nixpkgs']==NIXPKGS,'Toolchain différente')
    q=cert['qualification'];paquet=Path(q['sorties_nix']['metier'])
    exiger(re.fullmatch(r'/nix/store/[a-z0-9]{32}-mrjam-metier-[a-f0-9]{12}',str(paquet)), 'Paquet Nix non reconnu')
    exiger(sha(paquet/'bin/mrjam-metier')==q['artefact_sha256'],'Binaire différent de la qualification')
    exiger(q['source_revision']==cert['revision_construction'],'Révision de construction incohérente')
    exiger(paquet.name.endswith(q['source_revision'][:12]),'Nom du paquet incohérent')
    # La révision des opérateurs peut évoluer sans reconstruire le même graphe
    # Lisp. Aucune confiance dans le seul nom de révision ou dans un fichier .ok.
    sys.path.insert(0,str(root/'vps/scripts'))
    from assemblage import compilation_entrees, catalogue, entrees
    sources={n:root/n for n in cert['manifest']['sources']}
    sources['vps']=root/'vps'
    exiger(compilation_entrees(sources)==q['sources_lisp_sha256'],'Graphe Lisp différent de l’image')
    exiger(json.loads((root/'vps/assemblage/manifest.json').read_text())==cert['manifest'],'Manifeste différent')
    suites=catalogue()
    exiger(set(cert['recus_locaux_sha256'])==set(suites),'Catalogue incomplet')
    for nom,suite in suites.items():
        p=root/'recus'/(nom+'.json');r=json.loads(p.read_text())
        exiger(sha(p)==cert['recus_locaux_sha256'][nom] and r['format']==1
               and r['resultat']=='succes' and r['confiance']=='locale-non-attestee'
               and r['autorise_publication'] is False and all(c==0 for c in r['codes']),
               'Reçu local refusé : '+nom)
        i=r['identite']
        entrees_sources=sources
        if suite.get('style_consomme_par'):
            composant=suite['style_consomme_par'];edge=cert['manifest']['frontends'][composant]
            style=root/'styles-consommes'/composant
            exiger(cert.get('styles_consommes',{}).get(composant,{}).get('revision')==edge['revision_style'],
                   'Révision Style consommée différente : '+composant)
            verrou=root/composant/edge['verrou_style']
            exiger(sha(verrou)==edge['sha256'],'Verrou Style différent : '+composant)
            format_empreintes=edge.get('format_empreintes','sha256')
            exiger(format_empreintes in ('sha256','git-blob-sha1'),
                   'Format de verrou Style inconnu : '+composant)
            for fichier,empreinte in json.loads(verrou.read_text())['fichiers'].items():
                exiger(not Path(fichier).is_absolute() and '..' not in Path(fichier).parts,
                       'Chemin de verrou Style non borné')
                if format_empreintes=='git-blob-sha1':
                    contenu=(style/fichier).read_bytes()
                    actuel=hashlib.sha1(b'blob '+str(len(contenu)).encode()+b'\0'+contenu).hexdigest()
                else:actuel=sha(style/fichier)
                exiger(actuel==empreinte,'Source Style différente : '+composant)
            entrees_sources=dict(sources,style=style)
        if suite.get('preuve_mcp'):
            import importlib.util
            spec=importlib.util.spec_from_file_location('preuve_mcp',root/'vps/scripts/qualifier-mcp.py')
            preuve=importlib.util.module_from_spec(spec);spec.loader.exec_module(preuve)
            reference=root/'reference-mcp'
            exiger(i.get('preuve_mcp')==preuve.verifier_reference(
                json.loads((reference/'qualification.json').read_text()),
                json.loads((reference/'qualification-trace-synthetique.json').read_text()),root/'vps'),
                'Preuve MCP conservée différente')
        exiger(i['definition']==hashlib.sha256(json.dumps(suite,sort_keys=True).encode()).hexdigest()
               and i['entrees']==entrees(suite,entrees_sources),'Entrées de qualification différentes : '+nom)
        if suite.get('candidat_metier'):
            exiger(i['candidat_metier']['sha256']==q['artefact_sha256'],'Suite sur une autre image : '+nom)
        if suite.get('candidat_frontend'):
            front=cert['frontends'][suite['candidat_frontend']]
            exiger(i['candidat_frontend']=={k:front[k] for k in ('revision','fichiers')},'Suite sur un autre frontend : '+nom)
    return cert


def etat(d):
    entree=Path('/etc/nixos/configuration.nix')
    return {'generation':str(Path('/run/current-system').resolve()),
      'demarrage':str(Path('/nix/var/nix/profiles/system').resolve()),
      'configuration_sha256':sha(entree),'configuration_cible':str(entree.resolve()),
      'configuration_lien':os.readlink(entree) if entree.is_symlink() else None,
      'publications':{n:str(Path('/srv')/n/'current') for n in ('vision','vision-interface','matheval','logique')},
      'cibles':{n:str((Path('/srv')/n/'current').resolve()) for n in ('vision','vision-interface','matheval','logique')},
      'tiers_pids':{n:commande(['systemctl','show',n,'-p','MainPID','--value'],d).decode().strip() for n in TIERS}}


def inventaire_etats():
    result={}
    for n,path in ETATS.items():
        p=Path(path)
        if not p.exists():result[n]={'present':False};continue
        s=p.lstat();exiger(stat.S_ISREG(s.st_mode) and s.st_nlink==1,'État durable non régulier')
        result[n]={'present':True,'mode':oct(stat.S_IMODE(s.st_mode)),
                   'uid':s.st_uid,'gid':s.st_gid,'octets':s.st_size}
    return result


def verifier_acces_postgresql(avant,apres):
    def lignes(s):return [l.strip() for l in s.splitlines() if l.strip() and not l.lstrip().startswith('#')]
    roles=('vision','vision_administration','vision_cycle','vision_admission',
           'vision_fermeture','vision_entretien','matheval_app')
    hba=['local vision '+','.join(roles[:-1])+' peer map=mrjam_metier',
         'local matheval matheval_app peer map=mrjam_metier']
    maps=['mrjam_metier mrjam-metier '+r for r in roles]
    exiger(lignes(apres['authentication'])==hba+lignes(avant['authentication']),
           'HBA : seuls les deux accès peer métier sont autorisés avant les règles préservées')
    exiger(lignes(apres['identMap'])==lignes(avant['identMap'])+maps,
           'IdentMap : seuls les sept rôles métier limités sont autorisés')


def preparer(revision):
    exiger(os.geteuid()==0 and re.fullmatch('[a-f0-9]{40}',revision),'Opérateur/révision refusés')
    os.umask(0o077)
    d=Path('/root/mrjam-assemblages')/revision
    exiger(d.is_dir() and not d.is_symlink() and stat.S_IMODE(d.stat().st_mode)==0o700,'Stage non privé')
    root=d/'payload';cert=verifier_bundle(root)
    exiger(cert['revision']==revision,'Bundle d’une autre révision')
    if (d/'preparation.json').exists():
        preuve=json.loads((d/'preparation.json').read_text())
        exiger(preuve['revision']==revision and preuve['artefact_sha256']==cert['qualification']['artefact_sha256']
               and etat(d)==preuve['avant'],'Préparation enregistrée ou état actif différents')
        print(json.dumps({'revision':revision,'preparation_reutilisee':True,'activation':False}))
        return
    avant=etat(d)
    exiger(avant['generation']==avant['demarrage'],'Bascule concurrente')
    exiger(commande(['nix-instantiate','--find-file','nixpkgs'],d).decode().strip()==NIXPKGS,'Nixpkgs installé différent')
    commande(['systemctl','is-active',*TIERS,'nginx','postgresql','vision','matheval'],d)
    exiger(shutil.disk_usage('/').free>10*1024**3,'Espace insuffisant')
    # Aucun secret lu. Le corpus et la version sont issus de la source qualifiée.
    bank=json.loads((root/'matheval/research/bank.json').read_text())
    version=bank['version'];exiger(re.fullmatch('[A-Za-z0-9._-]+',version),'Version corpus invalide')
    public=Path('/srv/mrjam-assemblages')/revision
    if public.exists():
        exiger(not public.is_symlink(),'Ressources redirigées')
        for nom,front in cert['frontends'].items():
            fichiers={str(p.relative_to(public/nom)):sha(p) for p in (public/nom).rglob('*') if p.is_file()}
            exiger(fichiers==front['fichiers'],'Ressources présentes différentes')
    else:
        public.parent.mkdir(mode=0o755,exist_ok=True)
        public.mkdir(mode=0o755)
        for nom in cert['frontends']:shutil.copytree(root/'frontends'/nom,public/nom)
    for p in (public,*public.rglob('*')):
        exiger(not p.is_symlink(),'Lien dans les ressources')
        p.chmod(0o755 if p.is_dir() else 0o644)
    params={'configuration':avant['configuration_cible'],
            'paquet':cert['qualification']['sorties_nix']['metier'],
            'documentVision':str(public/'vision'),
            'ressourcesMatheval':str(public/'matheval'),
            'bankVersion':version}
    args=['nix-instantiate','-I','nixpkgs='+NIXPKGS,'--eval','--strict','--json',root/'vps/scripts/monolithe-config.nix']
    for k,v in params.items():args.extend(['--argstr',k,v])
    r=json.loads(commande(args,d))
    (d/'evaluation-privee.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n')
    exiger(r['avant']==avant['generation'],'Les sources actives ne reproduisent pas le système')
    verifier_acces_postgresql(r['postgresAccesAvant'],r['postgresAccesApres'])
    exiger(r['assertions'] and r['invariantAvant']==r['invariantApres'],'Un service préservé changerait')
    expression='(import '+str(root/'vps/scripts/monolithe-evaluation.nix')+' { '+''.join(k+'='+json.dumps(v)+'; ' for k,v in params.items())+'}).moduleCandidate'
    candidate=d/'configuration-candidate.nix'
    candidate.write_text('{ imports = [ '+json.dumps(avant['configuration_cible'])+' '+expression+' ]; }\n')
    racines=Path('/nix/var/nix/gcroots/mrjam-metier')/revision;racines.mkdir(parents=True,exist_ok=True)
    for n,p in {'avant':avant['generation'],'nixpkgs':NIXPKGS,'image':params['paquet'],
                'outils':cert['qualification']['sorties_nix']['outils']}.items():
        lien=racines/n
        if lien.is_symlink():exiger(str(lien.resolve())==str(Path(p).resolve()),'Racine Nix différente')
        else:exiger(not lien.exists(),'Racine concurrente');lien.symlink_to(p)
    construit=commande(['nix-build','<nixpkgs/nixos>','-A','system','-I','nixpkgs='+NIXPKGS,
        '-I','nixos-config='+str(candidate),'--out-link',racines/'candidat','--max-jobs','1','--cores','2'],d).decode().strip()
    exiger(construit==r['apres'],'Construction différente de l’évaluation')
    commande(shlex.split(r['nginx'])+['-t'],d)
    simulation=commande([Path(construit)/'bin/switch-to-configuration','dry-activate'],d,rapport_complet=True).decode()
    (d/'simulation-privee.txt').write_text(simulation)
    import importlib.util
    spec=importlib.util.spec_from_file_location('simulation_systeme',Path(__file__).with_name('simulation-systeme.py'))
    lecteur=importlib.util.module_from_spec(spec);spec.loader.exec_module(lecteur)
    # hba_file/ident_file sont postmaster dans PostgreSQL17 : leurs nouveaux
    # chemins Nix exigent le restart PG, puis son consommateur Keycloak.
    # Versions/dataDir/paramètres hors accès et unités IdP restent invariants.
    proteges=[n if n.endswith('.timer') else n+'.service' for n in TIERS if n!='keycloak']
    lecteur.verifier(simulation,proteges)
    exiger(etat(d)==avant,'État modifié pendant préparation')
    promotion=json.loads((d/'promotion.json').read_text())
    preuve={'format':1,'revision':revision,'run_ci':promotion['run_ci'],'avant':avant,'candidat':construit,
            'configuration':str(candidate),'parametres':params,'etats_durables':inventaire_etats(),
            'artefact_sha256':cert['qualification']['artefact_sha256'],
            'systeme_construit':True,'activation':False,'sauvegarde_actuelle_requise':True,
            'redemarrages_dependances_autorises':['postgresql','keycloak'],
            'restauration_acl_et_retour_restants':True}
    (d/'preparation.json').write_text(json.dumps(preuve,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in preuve.items() if k not in ('avant','parametres','etats_durables')},ensure_ascii=False))


if __name__=='__main__':
    try:
        with open('/root/mrjam-assemblage.lock','a') as f:
            fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);preparer(sys.argv[1])
    except Exception as erreur:
        if len(sys.argv)==2 and re.fullmatch('[a-f0-9]{40}',sys.argv[1]):
            d=Path('/root/mrjam-assemblages')/sys.argv[1]
            if d.is_dir() and not d.is_symlink():
                (d/'erreur-preparation-privee.log').write_text(traceback.format_exc())
        frames=[{'fichier':Path(f.filename).name,'ligne':f.lineno} for f in traceback.extract_tb(erreur.__traceback__)]
        # Nos ValueError/RuntimeError contiennent des règles fixes ou un nom de
        # commande/code, jamais une sortie de processus ou des données métier.
        print(json.dumps({'preparation':'refusee','exception':type(erreur).__name__,'pile':frames,
            'regle':str(erreur) if type(erreur) in (ValueError,RuntimeError) else 'Diagnostic privé requis'},ensure_ascii=False),file=sys.stderr)
        sys.exit(1)
