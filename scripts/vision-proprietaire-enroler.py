"""Enrôlement après preuve réelle d'activation réservée seulement."""
import argparse
import base64
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import urllib.request
import traceback

ROOT = Path(__file__).resolve().parents[1]
ETAPE = 'demarrage'


def charger(nom, fichier):
    s=importlib.util.spec_from_file_location(nom,ROOT/'scripts'/fichier)
    m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m


def exiger(ok):
    if not ok: raise ValueError('Enrôlement privé refusé')


def lire_dans(identite, dossier, nom):
    fd=os.open(dossier,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try: return json.loads(identite.lire(fd,nom))
    finally: os.close(fd)


def gate(revision, activation, preparation, candidat):
    exiger(isinstance(activation,dict) and type(activation.get('version')) is int and activation['version']==1 and re.fullmatch('[a-f0-9]{40}',activation.get('infrastructure','')))
    exiger(activation.get('preparation')==preparation['infrastructure'] and
        activation.get('systeme_amorcage')==preparation['systeme_amorcage'] and
        activation.get('systeme_ancien')==candidat['audit']['systeme'] and
        activation.get('vision')==candidat['vision'] and activation.get('style')==candidat['style'])
    exiger(all(activation.get(k) is True for k in ('activation_reservee','generation_enregistree','retour_neutralise',
        'copie_locale_chiffree','copie_froide_chiffree','postgres_prive','services_conserves')))
    exiger(all(activation.get(k) is False for k in ('mode_vision_oidc','inscriptions','identite_humaine')))
    # Cette vérification de reçu ne suffit pas : l'appelant vérifie aussi les
    # marqueurs privés, les chemins système et les services effectivement actifs.


def dechiffrer(enveloppe, executable):
    v=base64.b64decode(enveloppe.strip(),validate=True)
    exiger(len(v)<8192 and v.startswith(b'age-encryption.org/v1\n'))
    fd=os.open('/etc/ssh/ssh_host_ed25519_key',os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        info=os.fstat(fd)
        exiger(stat.S_ISREG(info.st_mode) and info.st_uid==0 and info.st_nlink==1 and
            stat.S_IMODE(info.st_mode)==0o600 and info.st_size<8192)
        r=subprocess.run([executable,'--decrypt','-i','/proc/self/fd/'+str(fd)],pass_fds=(fd,),input=v,
            capture_output=True,timeout=15)
        exiger(r.returncode==0 and len(r.stdout)<8192)
        return json.loads(r.stdout)
    finally: os.close(fd)


class SansRedirection(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs): return None


class ApiPrivee:
    def __init__(self,token):
        self.token=token
        self.opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),SansRedirection())
    def __call__(self,path,body=None,method=None):
        exiger(isinstance(path,str) and path.startswith('/admin/realms/mrjam/') and
            not any(c in path for c in ('\r','\n','#')))
        headers={'Host':'log.mrj.am','X-Forwarded-Proto':'https','X-Forwarded-Port':'443',
            'Authorization':'Bearer '+self.token}
        data=None
        if body is not None:
            data=json.dumps(body).encode();headers['Content-Type']='application/json'
        with self.opener.open(urllib.request.Request('http://127.0.0.1:8085'+path,data,headers,method=method),timeout=15) as r:
            value=r.read(1048577);exiger(len(value)<=1048576)
            result=json.loads(value) if value else None
            if method in ('POST','PUT'):return r.status,result,r.headers
            exiger(r.status==200);return result


def main(revision, observer=False):
    global ETAPE
    ETAPE='preuve_activation'
    exiger(os.geteuid()==0 and re.fullmatch('[a-f0-9]{40}',revision) is not None)
    os.umask(0o077)
    dossier=Path('/root/vision-proprietaire-operations')/revision
    exiger(ROOT==dossier/'source')
    construction=charger('construction','vision-identite-construire.py')
    identite=charger('import_identite','identite-preparer.py')
    preparer=charger('prepare_amorcage','vision-identite-amorcage-preparer.py')
    compte_module=charger('compte_initial','identite-proprietaire.py')
    controle=charger('controle_identite','identite-amorcage-controle.py')
    observation=charger('observation_initiale','vision-proprietaire-observation.py')
    notes_module=charger('notes_initiales','identite-session-proprietaire.py')
    boucle=charger('boucle_identite','vision-identite-boucle-locale.py')
    for p in (dossier.parent,dossier,ROOT):construction.dossier_prive(p)
    candidat=json.loads((ROOT/'operations/vision-multiutilisateur-candidat.json').read_text())
    preparation=json.loads((ROOT/'operations/vision-identite-amorcage-qualification.json').read_text())
    activation=json.loads((ROOT/'operations/vision-identite-amorcage-activation.json').read_text())
    gate(revision,activation,preparation,candidat)
    essai=Path('/root/vision-identite-amorcage-essais')/activation['infrastructure']
    prepare=Path('/root/vision-identite-amorcage-operations')/preparation['infrastructure']
    for p in (essai.parent,essai,prepare.parent,prepare):construction.dossier_prive(p)
    exiger(lire_dans(identite,essai,'activation.json')==activation and
        lire_dans(identite,prepare,'amorcage.json')==preparation)
    resume=lire_dans(identite,prepare,'evaluation-privee.json')
    preparer.verifier_resume(resume,candidat,preparation['paquet'])
    outils=Path(activation['systeme_amorcage'])/'sw/bin'
    def verifier_actif():
        exiger(all(str(p.resolve())==activation['systeme_amorcage'] for p in
            (Path('/run/current-system'),Path('/nix/var/nix/profiles/system'))))
        exiger(Path('/etc/nixos/configuration.nix').resolve()==essai/'entree.nix')
        fd=os.open(essai,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            for nom in ('commence','teste','enregistre'):exiger(identite.lire(fd,nom,0)=='')
            for nom in ('echec','retour-commence','retour-termine'):
                try:identite.lire(fd,nom,0)
                except FileNotFoundError:continue
                exiger(False)
        finally:os.close(fd)
        exiger(str(Path('/srv/vision/current').resolve())==candidat['audit']['vision'] and
            construction.preparation.socle.source_fournisseur_active()==candidat['audit']['fournisseur'])
        construction.commande(outils/'systemctl','is-active','sshd','nginx','postgresql','vision','matheval','mrj-auth',
            'mrjam-amorcage-postgresql','mrjam-amorcage-identite','mrjam-amorcage-sauvegarde.timer')
        for nom,unite in resume['unites_essentielles'].items():
            exiger(str(Path('/etc/systemd/system/'+nom+'.service').resolve().parent)==unite)
        for nom,cle in (('mrjam-amorcage-identite','unite_identite'),('mrjam-amorcage-postgresql','unite_cluster')):
            exiger(str(Path('/etc/systemd/system/'+nom+'.service').resolve().parent)==resume[cle])
        for nom,attributs in {'mrjam-amorcage-identite':{'DynamicUser':'yes','User':'keycloak','NoNewPrivileges':'yes'},
                'mrjam-amorcage-postgresql':{'User':'postgres','NoNewPrivileges':'yes'}}.items():
            for cle,valeur in attributs.items():
                exiger(construction.commande(outils/'systemctl','show',nom,'--property='+cle,'--value').strip()==valeur)
        exiger(boucle.verifier(construction.commande(outils/'ss','-Hltpn','sport = :8085')))
    verifier_actif()
    ETAPE='import_prive'
    destination=Path('/var/lib/mrjam-identite')
    identite.preparer(ROOT/'operations/identite/realm.json',destination,destination/'proton-smtp.json',controler=True)
    fd=os.open(destination,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        secret=identite.lire(fd,'amorcage-admin.secret',128).strip()
        realm=json.loads(identite.lire(fd,'mrjam-realm.json'))
    finally:os.close(fd)
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),SansRedirection())
    ETAPE='api_privee'
    token=controle.api(opener,'/realms/master/protocol/openid-connect/token',formulaire={
        'grant_type':'password','client_id':'admin-cli','username':'amorcage-local','password':secret})['access_token']
    api=ApiPrivee(token)
    # Vérifier le flux de preuve avant le premier courriel, pas après la réponse humaine.
    ETAPE='methodes_pwd_otp'
    ids=observation.executions(api,preparer.outil(resume,'runuser_paquet','runuser'),resume['postgres_paquet']+'/bin/psql')
    ETAPE='enveloppe_contact'
    contact=dechiffrer((ROOT/'operations/vision-proprietaire.age.b64').read_bytes(),preparer.outil(resume,'age_paquet','age'))
    compte_module.verifier_enveloppe(contact)
    ETAPE='etat_durable'
    state=Path('/var/lib/mrjam-proprietaire')
    try:state.mkdir(mode=0o700)
    except FileExistsError:pass
    construction.dossier_prive(state)
    fd=os.open(state,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    lock=identite.ouvrir_prive(fd,'enrolement.lock',os.O_RDWR|os.O_CREAT,maximum=0)
    try:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        def lire(nom):
            try:return json.loads(identite.lire(fd,nom,16384))
            except FileNotFoundError:return None
        def ecrire(nom,valeur):identite.ecrire(fd,nom,json.dumps(valeur))
        enregistrer=lire('compte.json')
        controle.verifier(secret,realm,opener=opener,sujet_proprietaire=enregistrer['sujet'] if enregistrer else None)
        if lire('executions.json') is None:ecrire('executions.json',ids)
        else:exiger(lire('executions.json')==ids)
        if observer:
            exiger(enregistrer is not None and lire('courriel-accepte') is not None)
            compte_module.preparer_compte(api,contact,lire,ecrire)
            actuel=api('/admin/realms/mrjam/users/'+enregistrer['sujet'])
            credentials=api('/admin/realms/mrjam/users/'+enregistrer['sujet']+'/credentials')
            exiger(actuel.get('enabled') is True and actuel.get('emailVerified') is True and actuel.get('requiredActions',[])==[] and
                {c.get('type') for c in credentials}=={'password','otp'})
            valeurs=observation.sessions(preparer.outil(resume,'runuser_paquet','runuser'),resume['postgres_paquet']+'/bin/psql',enregistrer['sujet'])
            maintenant=int(__import__('time').time())
            exiger(any(notes_module.verifier_notes(v,ids,maintenant) for v in valeurs))
            preuve=dict(version=1,issuer=compte_module.ISSUER,sujet=enregistrer['sujet'],pwd_otp_frais=True,date=maintenant)
            ecrire('connexion-'+str(maintenant)+'.json',preuve)
            verifier_actif()
            print(json.dumps(dict(compte_initial_verifie=True,connexion_pwd_otp_fraiche=True,inscriptions=False,mode_vision_oidc=False)))
            return
        ETAPE='compte_et_courriel'
        rapport=compte_module.preparer_compte(api,contact,lire,ecrire)
        verifier_actif()
        ETAPE='copie_identite'
        construction.commande(outils/'systemctl','start','mrjam-amorcage-sauvegarde',timeout=120)
        exiger(construction.commande(outils/'systemctl','show','mrjam-amorcage-sauvegarde',
            '--property=Result','--value').strip()=='success')
        verifier_actif()
        print(json.dumps(rapport))
    finally:os.close(lock);os.close(fd)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('revision');p.add_argument('--observer',action='store_true');a=p.parse_args()
    try:main(a.revision,a.observer)
    except Exception:
        # Le traceback reste sous le dossier root de cette opération, jamais Actions.
        try:
            dirfd=os.open(ROOT.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
            try:
                info=os.fstat(dirfd);exiger(info.st_uid==0 and stat.S_IMODE(info.st_mode)==0o700)
                fd=os.open('diagnostic-proprietaire-prive.log',os.O_WRONLY|os.O_CREAT|os.O_APPEND|os.O_NOFOLLOW|os.O_NONBLOCK,0o600,dir_fd=dirfd)
                try:
                    info=os.fstat(fd);exiger(stat.S_ISREG(info.st_mode) and info.st_uid==0 and info.st_nlink==1 and stat.S_IMODE(info.st_mode)==0o600 and info.st_size<262144)
                    os.write(fd,traceback.format_exc().encode()[:262144-info.st_size]);os.fsync(fd)
                finally:os.close(fd)
            finally:os.close(dirfd)
        except Exception:pass
        print(json.dumps(dict(enrolement_refuse=True,etape=ETAPE,inscriptions=False,mode_vision_oidc=False)))
        raise SystemExit(1)
