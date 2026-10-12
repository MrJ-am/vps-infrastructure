"""SBCL propre sous un autre UID : parent interdit puis copies privées accessibles.

Docker déjà approuvé, sans réseau, Nix en lecture seule, données synthétiques.
L'image interactive n'est ni redémarrée ni utilisée comme artefact de test.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
IMAGE='mirror.gcr.io/pgvector/pgvector@sha256:40b404964359299eefdd5f8518facf1886c562848cf4de13b6eaf91cb70c2b87'


def verifier():
    executable=Path(os.environ['MRJAM_TEST_EXECUTABLE'])
    q=json.loads(executable.with_suffix('.qualification.json').read_text())
    outils=Path(q['sorties_nix']['outils'])
    nom='mrjam-restauration-uid-'+uuid.uuid4().hex[:12]
    def docker(*args,check=True,input=None):
        return subprocess.run(['docker',*map(str,args)],text=True,input=input,capture_output=True,check=check)
    docker('run','--detach','--name',nom,'--network','none','--env','POSTGRES_HOST_AUTH_METHOD=trust',
           '--mount','type=bind,src=/nix/store,dst=/nix/store,readonly',IMAGE)
    try:
        for _ in range(100):
            if docker('exec',nom,'pg_isready','-h','127.0.0.1','-U','postgres',check=False).returncode==0:break
            time.sleep(.1)
        else:raise AssertionError('PostgreSQL isolé indisponible')
        with tempfile.TemporaryDirectory(prefix='restauration-sources-',dir=ROOT/'state') as tmp:
            # Reproduire le fichier privé de l'opérateur : son propriétaire
            # peut le lire, postgres ne peut pas traverser son parent. La
            # transmission stdin conserve les méta-commandes psql et la
            # transaction sans modifier ces permissions.
            sql=Path(tmp)/'roles-fixture.sql'
            sql.write_text('\\connect postgres\nBEGIN; SELECT current_user; COMMIT;\n')
            docker('exec',nom,'mkdir','-p','/root/mrjam-operateur')
            docker('exec',nom,'chmod','700','/root/mrjam-operateur')
            docker('cp',sql,nom+':/root/mrjam-operateur/roles-fixture.sql')
            refuse=docker('exec',nom,'runuser','-u','postgres','--','psql','-XAtq',
                '--set=ON_ERROR_STOP=1','--file=/root/mrjam-operateur/roles-fixture.sql',check=False)
            assert refuse.returncode!=0 and 'Permission denied' in refuse.stderr
            transmis=docker('exec','-i',nom,'runuser','-u','postgres','--','psql','-XAtq',
                '--set=ON_ERROR_STOP=1','--file=-',input=sql.read_text())
            assert transmis.stdout.strip()=='postgres'
            assert docker('exec',nom,'runuser','-u','postgres','--','test','-x','/root/mrjam-operateur',check=False).returncode==1
            # Même publication que sur le VPS : fichiers publics corrects,
            # parent créé sous umask0077. Lecture réellement refusée à un
            # autre UID, puis possible après correction limitée au parent.
            pub='/srv/mrjam-assemblages';doc=pub+'/fixture/vision/app.html'
            docker('exec',nom,'mkdir','-p',pub+'/fixture/vision')
            docker('exec',nom,'sh','-c','printf document-synthetique > '+doc)
            docker('exec',nom,'chmod','700',pub)
            docker('exec',nom,'chmod','755',pub+'/fixture',pub+'/fixture/vision')
            docker('exec',nom,'chmod','644',doc)
            assert docker('exec',nom,'runuser','-u','nobody','--','cat',doc,check=False).returncode!=0
            docker('exec',nom,'chmod','755',pub)
            assert docker('exec',nom,'runuser','-u','nobody','--','cat',doc).stdout=='document-synthetique'
            assert docker('exec',nom,'runuser','-u','nobody','--','test','-x','/root/mrjam-operateur',check=False).returncode==1
            source=Path(tmp)/'sources';atelier=Path(os.environ.get('MRJAM_ATELIER',ROOT.parent))
            chemins={'vps':ROOT,'vision':atelier/'vision','matheval':atelier/'M-moire'}
            noms={'vps':'vps','vision':'vision','matheval':'M-moire'}
            for f in list(q['sources_lisp_sha256'])+['vps/tests/restauration-etats.lisp',
                'vps/assemblage/oidc/charger-dependances.lisp']:
                c,r=f.split('/',1);p=source/noms[c]/r;p.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(chemins[c]/r,p)
            # Uniquement ces répertoires propres au conteneur, pas le store ou
            # un montage de sources modifiable ; l'autre UID est nobody.
            for parent in ('/tmp/parent-prive','/var/lib/mrjam-restauration-test'):
                docker('exec',nom,'mkdir','-p',parent+'/http/etats')
                docker('cp',source,nom+':'+parent+'/http/sources')
                docker('exec',nom,'test','-f',parent+'/http/sources/vps/tests/restauration-etats.lisp')
                docker('exec',nom,'chown','-R','nobody:nogroup',parent+'/http')
                docker('exec',nom,'chmod','-R','go-rwx',parent+'/http')
            docker('exec',nom,'chmod','700','/tmp/parent-prive')
            docker('exec',nom,'chown','postgres:nogroup','/var/lib/mrjam-restauration-test')
            docker('exec',nom,'chmod','710','/var/lib/mrjam-restauration-test')
            def lancer(parent):
                env=['PATH='+os.environ['PATH'],'LANG=C.UTF-8',
                     'MRJAM_LIBCRYPTO='+str(outils/'openssl/lib/libcrypto.so.3'),
                     'MRJAM_LIBSQLITE='+str(outils/'sqlite/lib/libsqlite3.so.0'),
                     'MRJAM_ETATS_ISOLES='+parent+'/http/etats','AGE='+str(outils/'age/bin/age'),
                     'MRJAM_AGE_RECIPIENT=age15zfsttzkz0n553mgq07czxk98j65y6pg47563c7gvneq65dmfgjs3x0x0l']
                return docker('exec',nom,'runuser','-u','nobody','--','env','-i',*env,
                              outils/'sbcl/bin/sbcl','--script',parent+'/http/sources/vps/tests/restauration-etats.lisp',check=False)
            mauvais=lancer('/tmp/parent-prive')
            # SBCL peut classer un fichier inaccessible comme inexistant ;
            # constater indépendamment existence et accès sous les deux UID.
            assert docker('exec',nom,'runuser','-u','nobody','--','test','-r',
                          '/tmp/parent-prive/http/sources/vps/tests/restauration-etats.lisp',check=False).returncode==1
            assert mauvais.returncode!=0 and 'FILE-' in mauvais.stderr and 'restauration-etats.lisp' in mauvais.stderr
            bon=lancer('/var/lib/mrjam-restauration-test')
            if bon.returncode:raise AssertionError(bon.stderr[-6000:]) # fixture synthétique uniquement
            assert 'Copies SQLite initialisées ; aucun transport ni traitement exécuté.' in bon.stdout
            print('SBCL propre/autre UID : parent privé refusé ; sources/FASL et quatre états SQLite privés initialisés via parent accessible, sans SMTP/IdP ni réseau.')
            print('PostgreSQL/autre UID : fichier opérateur privé refusé ; mêmes méta-commandes/transaction exécutées par stdin, permissions inchangées.')
            print('Ressource publique/autre UID : parent0700 refuse la lecture ; parent0755 permet les mêmes octets, bundle privé toujours inaccessible.')
    finally:docker('rm','--force','--volumes',nom)


if __name__=='__main__':verifier()
