"""Publication coordonnée d'interfaces, sans nouvelle migration ni changement de génération."""
import fcntl, hashlib, importlib.util, json, os, re, shlex, subprocess, sys, tarfile, time
from pathlib import Path
from corrections_artefacts import lire as lire_interface
from logique_artefact import exiger_publication

spec = importlib.util.spec_from_file_location('publication_vision', Path(__file__).with_name('vision-refonte-deployer.py'))
v = importlib.util.module_from_spec(spec); spec.loader.exec_module(v)
exiger, executer, sauver, empreinte = v.exiger, v.executer, v.sauver, v.empreinte
PROJETS = ('vision', 'vision-interface', 'logique', 'matheval')
RACINE = Path('/root/publications-interfaces')


def references(source):
    r = json.loads((source/'operations/interfaces-candidat.json').read_text())
    exiger(len({p['style'] for p in r['applications'].values()}) == 1, 'Styles différents')
    for p in r['applications'].values():
        exiger(all(re.fullmatch('[0-9a-f]{40}', p[k]) for k in ('application','style','signature')), 'Révision incomplète')
        exiger(p['ci']['conclusion'] == 'success' and p['ci']['revision'] == p['application'], 'CI différente')
    for nom, h in r['archives'].items():
        exiger(empreinte(source/'vendor/interfaces'/nom) == h, 'Archive altérée : '+nom)
    return r


def lire_tar(archive):
    with tarfile.open(archive, 'r:gz') as t:
        fichiers = {}; total = 0
        for p in t.getmembers():
            nom = Path(p.name)
            exiger(not nom.is_absolute() and '..' not in nom.parts and not p.issym() and not p.islnk(), 'Chemin TAR interdit')
            exiger(p.isdir() or p.isfile(), 'Type TAR interdit')
            if p.isfile():
                total += p.size
                exiger(total < 128*1024*1024 and p.name not in fichiers, 'Archive TAR excessive ou doublon')
                fichiers[p.name] = t.extractfile(p).read()
        return fichiers


def verifier(source):
    r = references(source)
    interfaces = {p:lire_interface(source,p,r['applications'][p],repertoire='interfaces') for p in ('vision','logique')}
    serveur = lire_tar(source/'vendor/interfaces/vision-source.tar.gz')
    exiger(serveur['revision-application.txt'].decode().strip() == r['applications']['vision']['application'], 'Source Vision différente')
    memoire = lire_tar(source/'vendor/interfaces/matheval.tar.gz')
    exiger(memoire['RELEASE'].decode().strip() == r['applications']['matheval']['application'], 'Version Mémoire différente')
    manifeste = json.loads(memoire['release-manifest.json'])
    exiger({n[10:] for n in memoire if n.startswith('docs/site/')} == set(manifeste), 'Inventaire Mémoire différent')
    for nom, h in manifeste.items():
        exiger(hashlib.sha256(memoire['docs/site/'+nom]).hexdigest() == h, 'Fichier Mémoire altéré : '+nom)
    return r, interfaces, serveur, memoire


def dossier(revision):
    exiger(re.fullmatch('[0-9a-f]{40}',revision), 'Révision exacte requise')
    return RACINE/revision


def lire(revision):
    d = dossier(revision)
    return d, json.loads((d/'preparation.json').read_text())


def inventaire(cible, prefixes):
    return {str(p.relative_to(cible)):empreinte(p) for prefixe in prefixes for p in (cible/prefixe).rglob('*')
            if p.is_file() and 'node_modules' not in p.parts and 'tests' not in p.parts}


def preserver_metier(avant, publications):
    for projet, prefixes, exceptions in [('vision',('src','migrations','scripts'),{'src/server.lisp','scripts/contrats.py','scripts/assembler-refonte.py','scripts/refonte.py'}), ('matheval',('server','research'),set())]:
        a,b = (inventaire(Path(e[projet]),prefixes) for e in (avant,publications))
        exiger({k:h for k,h in a.items() if k not in exceptions} == {k:h for k,h in b.items() if k not in exceptions}, 'Code métier ou schéma changé : '+projet)


def ecrire(cible, fichiers):
    exiger(not cible.exists(), 'Publication déjà préparée : '+str(cible))
    cible.mkdir(parents=True, mode=0o755)
    for nom, contenu in fichiers.items():
        p = cible/nom
        exiger(p.resolve().is_relative_to(cible.resolve()), 'Chemin sortant')
        p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(contenu)
    executer('chmod','-R','a+rX',cible)


def preparer(revision):
    d=dossier(revision); source=d/'source'; avant=v.etat(); v.services()
    exiger(not (d/'preparation.json').exists(), 'Opération déjà préparée')
    exiger(avant['systeme']==avant['demarrage'], 'Générations désynchronisées')
    r, interfaces, serveur, memoire=verifier(source)
    publications={p:'/srv/'+p+'/releases/'+r['applications']['vision' if p=='vision-interface' else p]['application'] for p in PROJETS}
    contenus={'vision':serveur,'vision-interface':interfaces['vision'][1],'logique':interfaces['logique'][1],'matheval':memoire}
    for p in PROJETS:ecrire(Path(publications[p]),contenus[p])
    manifeste={**interfaces['logique'][0],'hebergementConfirme':True,'publicationAutorisee':True,'preuveInfrastructure':revision}
    exiger_publication(manifeste)
    sauver(Path(publications['logique'])/'manifeste-preparation.json',manifeste)
    (Path(publications['logique'])/'manifeste-preparation.json').chmod(0o644)
    preserver_metier(avant,publications)
    nixpkgs=executer('nix-instantiate','--find-file','nixpkgs').decode().strip()
    executer('chown','-R','vision:vision',publications['vision'])
    executer('nix-shell','-I','nixpkgs='+nixpkgs,'-p','sbcl','--run','cd '+shlex.quote(publications['vision'])+' && sh build.sh')
    exiger((Path(publications['vision'])/'vision').stat().st_size>1000000, 'Binaire Vision absent')
    executer('chmod','-R','a+rX',publications['vision'])
    executer('chown','-R','matheval-deploy:matheval',publications['matheval'])
    executer('runuser','-u','matheval-deploy','--','npm','--prefix',publications['matheval']+'/server','ci','--omit=dev','--ignore-scripts')
    temoin=d/'timer-verifie'
    executer('systemd-run','--unit=interfaces-temoin-'+revision[:12],'--on-active=2s','--timer-property=AccuracySec=1s','/run/current-system/sw/bin/touch',temoin)
    for _ in range(15):
        if temoin.exists():break
        time.sleep(1)
    exiger(temoin.exists() and v.etat()==avant, 'Préparation ou retour autonome non confirmé'); v.services()
    sauver(d/'preparation.json',dict(revision=revision,avant=avant,publications=publications,python=sys.executable,nixpkgs=nixpkgs,
                                  fichiers={p:inventaire(Path(c),('',)) for p,c in publications.items()}))
    print(json.dumps({'avant':avant,'publications':publications,'schema_identique':True,'activation':False}))


def attendu(r):return {**r['avant'],**r['publications']}


def compatible_retour(r,courant):
    return all(courant[k]==r['avant'][k] for k in ('systeme','demarrage','configuration')) and all(courant[p] in (r['avant'][p],r['publications'][p]) for p in PROJETS)


def controler_fichiers(r):
    for p,c in r['publications'].items():
        exiger(inventaire(Path(c),('',))==r['fichiers'][p], 'Publication altérée : '+p)


def publier_matheval(cible):
    executer('runuser','-u','matheval-deploy','--','matheval-release',Path(cible).name)


def appliquer(revision):
    d,r=lire(revision)
    with (d/'bascule.lock').open('a') as verrou:
        fcntl.flock(verrou,fcntl.LOCK_EX)
        exiger(v.etat()==r['avant'] and not (d/'retour-engage').exists(), 'État modifié'); controler_fichiers(r)
        # Le publicateur Mémoire conserve son propre verrou, compte et contrôle de santé.
        publier_matheval(r['publications']['matheval'])
        executer('systemctl','stop','vision')
        for p in ('vision','vision-interface','logique'):v.lien(r['publications'][p],'/srv/'+p+'/current')
        executer('systemctl','start','vision'); v.services()
        exiger(v.etat()==attendu(r),'État différent du candidat'); sauver(d/'essai.json',v.etat())
    print('Trois applications activées sous retour autonome ; schémas et données conservés.')


def retour(revision):
    d,r=lire(revision)
    if (d/'enregistre').exists():return
    subprocess.run(['systemctl','stop','interfaces-appliquer-'+revision[:12]+'.service'],check=False,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    with (d/'bascule.lock').open('a') as verrou:
        fcntl.flock(verrou,fcntl.LOCK_EX)
        if (d/'enregistre').exists():return
        exiger((d/'engage').exists() and compatible_retour(r,v.etat()), 'État concurrent : retour refusé')
        (d/'retour-engage').touch(); executer('systemctl','stop','vision')
        for p in ('vision','vision-interface','logique'):v.lien(r['avant'][p],'/srv/'+p+'/current')
        executer('systemctl','start','vision'); publier_matheval(r['avant']['matheval']); v.services()
        sauver(d/'retour.json',{'etat':v.etat(),'restauration_base':False})
    executer('systemctl','stop','interfaces-retour-'+revision[:12]+'.timer')


def demarrer(revision):
    d,r=lire(revision)
    exiger(not any((d/n).exists() for n in ('engage','retour-engage','enregistre')) and v.etat()==r['avant'], 'Nouvelle préparation requise')
    (d/'engage').touch(); script=d/'source/scripts/publication_interfaces.py'
    commun=['--setenv=PATH='+os.environ['PATH'],r['python'],script]
    executer('systemd-run','--unit=interfaces-retour-'+revision[:12],'--on-active=20m','--timer-property=AccuracySec=1s',*commun,'retour',revision)
    executer('systemctl','is-active','interfaces-retour-'+revision[:12]+'.timer')
    executer('systemd-run','--wait','--pipe','--unit=interfaces-appliquer-'+revision[:12],*commun,'appliquer',revision)


def finaliser(revision):
    d,r=lire(revision)
    with (d/'bascule.lock').open('a') as verrou:
        fcntl.flock(verrou,fcntl.LOCK_EX)
        exiger((d/'essai.json').exists() and not (d/'retour-engage').exists() and v.etat()==attendu(r), 'Essai non confirmé')
        controler_fichiers(r); v.services(); sauver(d/'termine.json',{'revision':revision,'etat':v.etat(),'schema_identique':True}); (d/'enregistre').touch()
    executer('systemctl','stop','interfaces-retour-'+revision[:12]+'.timer')


def constater(revision):
    d,r=lire(revision)
    exiger((d/'enregistre').exists() and not (d/'retour-engage').exists() and v.etat()==attendu(r), 'Publication non enregistrée')
    exiger(subprocess.run(['systemctl','is-active','--quiet','interfaces-retour-'+revision[:12]+'.timer']).returncode!=0,'Retour encore actif')
    controler_fichiers(r); v.services(); print((d/'termine.json').read_text())


if __name__=='__main__':
    if sys.argv[1]=='verifier':verifier(Path(__file__).resolve().parents[1]); print('Trois artefacts intègres, même style et révisions CI exactes.')
    else:
        exiger(os.geteuid()==0,'Exécution réservée au runner administratif'); os.umask(0o077)
        os.environ['VISION_REFONTE_ERREURS']=str(dossier(sys.argv[2])/'commande-echec-prive.log')
        {'preparer':preparer,'demarrer':demarrer,'appliquer':appliquer,'retour':retour,'finaliser':finaliser,'constater':constater}[sys.argv[1]](sys.argv[2])
