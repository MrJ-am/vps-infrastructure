"""Qualifier la récupération, l'interface et le retour autonome ; aucun essai actif."""
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import stat
import subprocess
import time
import zipfile

RECIPIENT = 'age1p95t4z0aafq7j4fl7cc9f0cjz8j03dtlmz56kec4lj6vwxrvzpqqnc53cc'
INTERFACE = '7aef73e8586d2788a75498e33ea605f88d3cb3fa9f7f14dadabd461e6eb812af'
MANIFESTE = 'cece6c7845dd11f81e28fbc5be402db6709889ccad8060d4c8509b42bd5fedf2'


def exiger(condition):
    if not condition: raise ValueError('Qualification de l’essai refusée')


def verifier_recuperation(resultat, confirmation):
    exiger(type(resultat.get('version')) is int and resultat['version'] == 1 and
        type(confirmation.get('version')) is int and confirmation['version'] == 1)
    attendus = dict(reference='vision-recuperation-20261010',
        infrastructure='6f0d38cddaabb6d685efcefc9b7b5036b0ef9950', execution=38049744292,
        chiffre_sha256='fa70adbc156d07ddf18e927a4d1bd31b38479db7ad30472a812dc27a5cfe3966',
        chiffre_octets=473596, cle_publique=RECIPIENT,
        verificateur_sha256='1603176030f81361dd3b81a4aac099219fac0f4f772267ba0b78d73254d9df3a',
        preuve_sha256='d755e4db6d3a9bbe87ad8bace264f4aec4db163a862337ee7683159f4d9ee85b')
    exiger(all(resultat.get(k) == v and confirmation.get(k) == v for k,v in attendus.items()))
    exiger(all(resultat.get(k) is True for k in ('restauration_vision_reelle','restauration_identite_reelle',
        'sqlite_integrite','accepte_par_relais')) and
        all(confirmation.get(k) is True for k in ('preuve_aleatoire_verifiee','fichiers_identiques_aux_copies_testees',
        'dechiffrement_complet','reception_confirmee_par_exploitant','copie_exterieure_verifiee')) and
        all(confirmation.get(k) is False for k in ('donnees_en_clair_ecrites','cle_privee_transmise',
        'sauvegarde_vps_complete','activation','inscriptions')) and
        confirmation.get('cle_publique_sha256') == hashlib.sha256(RECIPIENT.encode()).hexdigest())


def extraire_interface(archive, destination):
    exiger(hashlib.sha256(archive.read_bytes()).hexdigest() == INTERFACE and not destination.exists())
    with zipfile.ZipFile(archive) as z:
        noms = z.namelist()
        exiger(len(noms) == 23 and len(set(noms)) == 23 and 'manifest.json' in noms)
        for i in z.infolist():
            exiger(not Path(i.filename).is_absolute() and '..' not in Path(i.filename).parts and
                stat.S_ISREG(i.external_attr >> 16) and 0 < i.file_size < 2000000)
        contenu = z.read('manifest.json'); exiger(hashlib.sha256(contenu).hexdigest() == MANIFESTE)
        m = json.loads(contenu)
        exiger(m.get('formatVersion') == 1 and m.get('revisionApplication') == 'a9c51acac81510d7dc896f5daf4e6fb28a36b979' and
            m.get('revisionStyle') == '96fa28ac564b9492768837d4087608e83acc721b' and
            m.get('revisionSignature') == '17495b13cefa24473e37434b98336b27caec8cdf' and
            set(m['fichiers']) | {'manifest.json'} == set(noms))
        destination.mkdir(mode=0o700)
        for nom in noms:
            contenu = z.read(nom)
            exiger(nom == 'manifest.json' or hashlib.sha256(contenu).hexdigest() == m['fichiers'][nom])
            p = destination/nom; p.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
            with p.open('xb') as f: f.write(contenu)
            p.chmod(0o600)
    return m


def verifier_repertoires(rapport):
    regles=rapport.get('regles_connues',{})
    exiger(isinstance(regles,dict) and all(isinstance(r,dict) and
        all(type(v) is int for v in r.values()) for r in regles.values()))
    exiger(all(rapport.get(k) is True for k in ('resetup_identique_hors_triggers',
        'regles_existantes_hors_perimetre_identiques','lien_import_keycloak_nouveau_exact')) and
        rapport.get('fichiers_tmpfiles_ajoutes') == ['10-keycloak.conf'] and
        rapport.get('fichiers_tmpfiles_retires') == [] and
        regles == {
            'sauvegarde_amorcage':dict(avant=1,apres=1),
            'sauvegarde_commune':dict(avant=0,apres=1),
            'effacements_vision':dict(avant=0,apres=1)})
    return True


def verifier_dry(texte,repertoires_valides=False):
    texte=re.sub(r'\x1b\[[0-9;]*[A-Za-z]','',texte)
    exiger(len(texte)<1048576 and 'would activate the configuration' in texte and
        not re.search(r'would (?:restart systemd|stop swap)',texte))
    autorises = {'nginx.service','nginx-config-reload.service','postgresql.service','postgresql-setup.service',
        'vision.service','vision-bootstrap.service','vision-migrate.service','mrj-auth.service',
        'keycloak.service','mrjam-amorcage-identite.service','mrjam-amorcage-postgresql.service',
        'mrjam-amorcage-sauvegarde.service','mrjam-amorcage-sauvegarde.timer',
        'postgresqlBackup-vision.service','postgresqlBackup-vision.timer',
        'vision-gestion.service','vision-cycle.service','mrjam-admission.service','mrjam-fermeture.service',
        'mrjam-courriel.service','vision-purge.service','vision-purge.timer',
        'mrjam-sauvegarde.service','mrjam-sauvegarde.timer',
        'systemd-journald@identite.service','systemd-journald@identite.socket',
        'systemd-journald-varlink@identite.socket'}
    modifies=set()
    for action,noms in re.findall(r'would (stop|restart|reload|start) the following units: ([^\n]+)',texte):
        unites={u.strip() for u in noms.split(',')}
        special=unites & {'systemd-tmpfiles-resetup.service'}
        exiger(not special or (repertoires_valides is True and action in ('stop','start')))
        exiger(unites-special <= autorises)
        modifies.update(unites)
    return sorted(modifies)


def script_retour(d, ancien, outils, postgres, runuser, worker, *,
        configuration='/etc/nixos/configuration.nix', profil='/nix/var/nix/profiles/system',
        courant='/run/current-system', backend='/srv/vision/current',
        verrou_deploiement='/srv/vision/deploy.lock', unites='/run/systemd/system',
        socket_nouveau='/run/postgresql', socket_ancien='/run/mrjam-amorcage-postgresql'):
    """Opérateur autonome : état durable, fermeture des clients et identité courante.

    Les chemins alternatifs servent aux essais synthétiques ; la préparation
    de production ne les prend jamais depuis une requête ni un environnement.
    """
    valeurs=dict(d=str(d),ancien=str(ancien),outils=str(outils),postgres=str(postgres),
        runuser=str(runuser),worker=worker,configuration=configuration,profil=profil,
        courant=courant,backend=backend,verrou_deploiement=verrou_deploiement,
        unites=unites,socket_nouveau=socket_nouveau,socket_ancien=socket_ancien,
        gate='90-vision-retour-'+d.name[:12]+'.conf')
    corps=(Path(__file__).with_name('vision-essai-retour.sh')).read_text()
    return '#!'+str(outils/'bash')+'\n'+''.join(k+'='+shlex.quote(v)+'\n' for k,v in valeurs.items())+corps


def preparer(d, source, root, config, resume, revision, charger, commande, sauver):
    verifier_recuperation(json.loads((root/'operations/vision-recuperation-resultat.json').read_text()),
        json.loads((root/'operations/vision-recuperation-confirmation.json').read_text()))
    m=extraire_interface(root/'vendor/vision-multiutilisateur-interface.zip',d/'interface')
    expression=root/'scripts/vision-essai-generation.nix'
    candidat=json.loads((root/'operations/vision-multiutilisateur-candidat.json').read_text())
    args=[expression,'--argstr','configuration','/etc/nixos/configuration.nix','--argstr','source',source,
        '--argstr','fournisseur',candidat['audit']['fournisseur'],'--argstr','sourceInterface',d/'interface',
        '-I','nixpkgs='+candidat['audit']['nixpkgs']]
    r=json.loads(commande('nix-instantiate','--eval','--strict','--json',*args,'--attr','resume'))
    exiger(r['version']==1 and r['systeme_actif']==config['systeme'] and r['systeme_candidat']!=config['systeme'] and
        r['postgres_paquet']==resume['postgres_paquet'] and r['recipient_age']==RECIPIENT and
        r['fournisseur_source']==candidat['audit']['fournisseur'] and
        r['hors_vision_identite_conserve'] is True and r['preconditions_validees'] is True and
        r['bus_systeme_conserve'] is True and
        r['inscriptions'] is False and r['activation'] is False)
    construction=charger('construction_essai',root/'scripts/vision-identite-construire.py')
    for n in ('systeme_actif','systeme_candidat','backend_paquet','interface_store','nginx_paquet'):
        construction.store(r[n])
    systeme=commande('nix-build',*args,'--attr','systeme','--out-link',d/'generation-essai',
        '--max-jobs','1','--cores','2',timeout=1800).strip()
    exiger(systeme==r['systeme_candidat'] and (Path(r['backend_paquet'])/'app/vision').is_file())
    exiger(hashlib.sha256((Path(r['interface_store'])/'manifest.json').read_bytes()).hexdigest()==MANIFESTE)
    sauver('evaluation-essai.json',r)
    nginx=charger('nginx_essai',root/'scripts/vision-identite-amorcage-preparer.py')
    nginx.construction.preparation.DIAGNOSTIC = d/'diagnostic-prive.log'
    # Ce contrôle reprend le confinement natif déjà qualifié, en réseau privé.
    nginx.verifier_nginx(r,revision)
    lecteur=charger('lecteur_perimetre_essai',root/'scripts/vision-essai-diagnostiquer.py')
    repertoires=lecteur.comparer_repertoires(config['systeme'],systeme)
    sauver('repertoires-essai.json',repertoires)
    print(json.dumps(dict(perimetre_repertoires=repertoires)),flush=True)
    qualifies=verifier_repertoires(repertoires)
    dry=subprocess.run([str(Path(systeme)/'bin/switch-to-configuration'),'dry-activate'],
        capture_output=True,timeout=120)
    texte=(dry.stdout+dry.stderr).decode()
    fd=os.open(d,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    prive=charger('prive_essai',root/'scripts/identite-preparer.py')
    try: prive.ecrire(fd,'dry-activate-prive.txt',texte)
    finally: os.close(fd)
    exiger(dry.returncode==0)
    try:modifies=verifier_dry(texte,qualifies)
    except Exception:
        print(json.dumps(dict(simulation_refusee=True,**lecteur.classer(texte))),flush=True)
        raise
    # Une entrée persistante indépendante du futur lien /etc doit reproduire
    # exactement cette génération ; éviter le cycle de référence déjà corrigé.
    original=str(Path('/etc/nixos/configuration.nix').resolve())
    exiger(re.fullmatch(r'/root/vision-identite-amorcage-essais/[a-f0-9]{40}/entree.nix',original))
    parametres=dict(configuration=original,source=str(source),fournisseur=candidat['audit']['fournisseur'],
        sourceInterface=str(d/'interface'))
    entree='{ imports = [ '+json.dumps(original)+' ((import '+str(root/'scripts/vision-bascule-evaluation.nix')+' { '
    entree+=' '.join(k+' = '+json.dumps(v)+';' for k,v in parametres.items())
    entree+=' preconditionsValidees = true; }).moduleCandidate) ]; }\n'
    fd=os.open(d,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try: prive.ecrire(fd,'entree.nix',entree)
    finally: os.close(fd)
    reproduit=json.loads(commande('nix-instantiate','--eval','--strict','--json',
        root/'scripts/vision-identite-amorcage-systeme.nix','--argstr','configuration',d/'entree.nix',
        '-I','nixpkgs='+candidat['audit']['nixpkgs']))
    exiger(reproduit==systeme)
    outils=Path(config['systeme'])/'sw/bin'
    retour=script_retour(d,config['systeme'],outils,Path(resume['postgres_paquet']),
        Path(resume['runuser_paquet'])/'bin/runuser','vision-essai-'+revision[:12]+'.service')
    fd=os.open(d,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try: prive.ecrire(fd,'retour.sh',retour)
    finally: os.close(fd)
    (d/'retour.sh').chmod(0o700)
    commande(outils/'bash','-n',d/'retour.sh')
    commande(outils/'systemd-run','--unit=vision-essai-repetition-'+revision[:12],
        '--on-active=3s','--timer-property=AccuracySec=1s','--property=UMask=0077',
        '--collect',outils/'touch',d/'timer-repete')
    limite=time.monotonic()+20
    while not (d/'timer-repete').exists() and time.monotonic()<limite: time.sleep(1)
    exiger((d/'timer-repete').is_file())
    return dict(generation_complete_construite=True,configuration_nginx_native=True,
        dry_activate_qualifie=True,unites_dry=len(modifies),interface_exacte=True,fichiers_interface=len(m['fichiers']),
        nouvelle_cle_vision_identite=True,cle_personnelle_verifiee=True,copie_exterieure_verifiee=True,
        retour_autonome_prepare=True,retour_autonome_arme=False,production_modifiee=False,
        timer_independant_repete=True,
        entree_persistante_reproduite=True,
        donnees_production_modifiees=False,generation_active_modifiee=False,activation=False,inscriptions=False)
