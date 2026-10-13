"""Qualifier le provisionnement opérateur exact sur IdP synthétique isolé."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import base64
import subprocess
import gzip
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'))
from kanidm_reel import KanidmLocal, EchecQualification
from kanidm_politiques import code_totp,login_mfa

def main():
    spec=importlib.util.spec_from_file_location('native_ops',ROOT/'scripts/kanidm-api-privee.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    with KanidmLocal(os.environ['MRJAM_KANIDM'],os.environ['MRJAM_CURL']) as n:
        api=m.KanidmPrive(n.paquet,n.config,n.curl,ca=n.ca,port=n.port,
                          diagnostic=ROOT/'state/kanidm-operation-native-diagnostic.log')
        d=api.configurer_proprietaire({'name':'fixture-proprietaire','mail':'fixture-proprietaire@example.test'},n.root)
        assert set(d)=={'subject','client_secret','intent','admission_token'}
        op=api.login('idm_admin',api.recuperer('idm_admin'),n.root)
        profil=api.http('/v1/person/'+d['subject'],token=op)['attrs']
        assert profil['mail']==['fixture-proprietaire@example.test']
        assert profil['displayname']==profil['mail']
        group=api.http('/v1/group/mrjam-proprietaire-policy',token=op)['attrs']
        assert group['authsession_expiry']==['604800']
        assert group['credential_type_minimum']==['mfa']
        assert group['privilege_expiry']==['900']
        client=api.http('/v1/oauth2/mrjam-vision',token=op)['attrs']
        assert client['oauth2_strict_redirect_uri']==['true']
        assert client['oauth2_rs_origin']==['https://vision.mrj.am/auth/retour']
        token, _=api.http('/v1/credential/_exchange_intent',d['intent'])
        cu=api.http('/v1/credential/_update',[{'password':n.password},token])
        assert not cu['can_commit'] and 'MfaRequired' in cu['warnings']
        cu=api.http('/v1/credential/_update',['totpgenerate',token])
        totp=cu['mfaregstate']['TotpCheck']
        cu=api.http('/v1/credential/_update',[{'totpverify':[code_totp(totp),'fixture']},token])
        assert cu['can_commit']
        api.http('/v1/credential/_commit',token)
        n.nom='fixture-proprietaire'
        session=login_mfa(n,totp)
        payload=json.loads(base64.urlsafe_b64decode(session.split('.')[1]+'=='))
        assert payload['expiry']-payload['issued_at']==604800
        backup=n.root/'proprietaire-backup.json'
        api.commande('scripting','backup',str(backup))
        assert api.restaurer_verifier(backup,n.root/'restauration',d['subject'])
        stream=subprocess.run([str(n.paquet/'bin/kanidmd'),'-c',str(n.config),'scripting','backup'],
                              capture_output=True,check=True,timeout=45).stdout
        assert stream.startswith(b'\x1f\x8b') and isinstance(json.loads(gzip.decompress(stream)),dict)
        copie=n.root/'backup-stdout.json.gz';copie.write_bytes(stream);copie.chmod(0o600)
        assert api.restaurer_verifier(copie,n.root/'restauration-stdout',d['subject'])
        api.commande('disable-account','idm_admin')
        print(json.dumps({'provisionnement_operateur_reel':True,'sujet_neuf':True,
          'pseudo_mail_par_defaut':True,'mfa_obligatoire':True,'duree_role_7_jours':True,
          'fraicheur_administration_900_secondes':True,'redirection_stricte':True,
          'aucun_credential_admin_dans_lisp':True,'restauration_native_entrees_lues':True,
          'backup_stdout_gzip_restaure':True,'production':False}))
if __name__=='__main__':
    try: main()
    except Exception as e:
        print('Qualification opérateur refusée : '+type(e).__name__+
              (' : '+str(e) if type(e).__name__=='OperationRefusee' else ''),file=sys.stderr);sys.exit(1)
