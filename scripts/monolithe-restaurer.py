"""Qualifier ACL, lectures et retour sur une restauration récente chiffrée.

Pas d'écriture ni arrêt de production. Les deux exécutables utilisent uniquement
le cluster restauré, aucun SMTP/IdP, aucun contenu dans le rapport public.
"""
import importlib.util
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import signal
import sqlite3
import shlex
import socket
import subprocess
import sys
import time
import urllib.request
import datetime
import uuid
import fcntl
import traceback

sys.dont_write_bytecode=True

ROOT=Path(__file__).resolve().parents[1]


def module(nom,path):
    s=importlib.util.spec_from_file_location(nom,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m


def comparer_lectures(a,b,fenetres):
    """Même données, fenêtres vérifiées à chaque instant de lecture réel.

    now() et l'urgence/état dérivés peuvent changer entre deux transactions.
    Aucun champ durable/date/politique n'est exclu. Le callback recalcule la
    fenêtre complète avec vision_fenetre existante dans la copie PostgreSQL.
    """
    def projection(v):
        if not isinstance(v,dict) or not isinstance(v.get('maintenant'),str):raise ValueError('Lecture sans instant')
        instant=datetime.datetime.fromisoformat(v['maintenant'].replace('Z','+00:00'))
        if instant.tzinfo is None:raise ValueError('Lecture sans fuseau')
        attendues=fenetres(instant.isoformat());objets=v.get('objets')
        if not isinstance(objets,list):raise ValueError('Lecture sans objets')
        if len(objets)!=len(attendues) or {str(o.get('id')) for o in objets}!=set(attendues):raise ValueError('Objets restaurés divergents')
        resultat=[]
        for o in objets:
            f=o.get('fenetre')
            if f!=attendues[str(o['id'])]:raise ValueError('Fenêtre restaurée divergente')
            resultat.append({**o,'fenetre':{k:x for k,x in f.items() if k not in ('urgence','etat')}})
        return {**{k:x for k,x in v.items() if k!='maintenant'},'objets':resultat}
    return projection(a)==projection(b)


def main(revision):
    if os.geteuid()!=0 or not re.fullmatch('[a-f0-9]{40}',revision):raise ValueError('Opérateur/révision refusés')
    d=Path('/root/mrjam-assemblages')/revision
    prepare=json.loads((d/'preparation.json').read_text())
    if prepare['revision']!=revision:raise ValueError('Préparation incohérente')
    stage=module('mrjam_preparer',ROOT/'scripts/monolithe-preparer.py')
    if stage.etat(d)!=prepare['avant']:raise ValueError('État actif différent depuis préparation')
    cert=stage.verifier_bundle(d/'payload')
    backup=module('mrjam_backup',ROOT/'scripts/monolithe-sauvegarde.py')
    tables=module('mrjam_tables',ROOT/'scripts/verifier-tables.py')
    ancien=Path(prepare['avant']['cibles']['vision'])/'vision'
    image=Path(cert['qualification']['sorties_nix']['metier'])/'bin/mrjam-metier'
    outils=Path(cert['qualification']['sorties_nix']['outils'])
    # La sauvegarde indépendante vérifie toujours sa génération réelle.
    backup.GENERATION=prepare['avant']['generation']
    def qualifier(bin,isole,copies_etats):
        def sql(base,texte):return backup.sql(bin,isole,base,texte)
        avant={b:backup.schema(lambda q,b=b:sql(b,q)) for b in ('vision','matheval')}
        # Migration sur la copie exclusivement, propriétaire cible NOLOGIN.
        version=sql('vision','SELECT max(version) FROM vision_schema_migrations')
        backup.exiger(version in ('25','26','27'))
        if version=='25':sql('vision',(d/'payload/vision/migrations/026_autorisation_admission.sql').read_text())
        sql('vision',(d/'payload/vision/migrations/027_retablir_rls.sql').read_text())
        sql('vision',(d/'payload/vision/scripts/roles.sql').read_text())
        backup.commande(['runuser','-u','postgres','--',bin/'psql','-Xq','--set=ON_ERROR_STOP=1',
            '--host='+str(isole),'--dbname=vision','--file=-'],input=(ROOT/'assemblage/roles-metier.sql').read_bytes())
        for role in ('vision','vision_identite','vision_administration','vision_cycle','vision_admission',
                     'vision_fermeture','vision_entretien','matheval_app'):
            sql('postgres','ALTER ROLE '+role+' LOGIN')
        for b in ('vision','matheval'):tables.verifier(b,lambda q,b=b:sql(b,q))
        apres={b:backup.schema(lambda q,b=b:sql(b,q)) for b in ('vision','matheval')}
        del avant['vision']['public.vision_schema_migrations'];del apres['vision']['public.vision_schema_migrations']
        backup.exiger(avant==apres)
        # Socket privé, peer vérifié : le compte Unix Vision ne peut pas se
        # présenter comme postgres, propriétaire, identité ou autre compte.
        user=pwd.getpwnam('vision');os.chown(isole,-1,user.pw_gid);isole.chmod(0o710)
        roles=['vision','vision_administration','vision_cycle','vision_admission','vision_fermeture','vision_entretien','matheval_app']
        (isole/'data/pg_hba.conf').write_text('local all postgres peer\nlocal vision '+','.join(roles[:-1])+' peer map=qualification\nlocal matheval matheval_app peer map=qualification\nlocal all all reject\n')
        (isole/'data/pg_ident.conf').write_text(''.join('qualification vision '+r+'\n' for r in roles))
        backup.commande(['runuser','-u','postgres','--',bin/'pg_ctl','-D',isole/'data','reload'])
        essais=isole/'http';essais.mkdir(mode=0o700);os.chown(essais,user.pw_uid,user.pw_gid)
        wrapper=essais/'psql'
        wrapper.write_text('#!/bin/sh\nexec '+shlex.quote(str(bin/'psql'))+' -h '+shlex.quote(str(isole))+' -U vision -d vision "$@"\n')
        os.chown(wrapper,user.pw_uid,user.pw_gid);wrapper.chmod(0o700)
        proprietaire=json.loads(sql('vision',"SELECT to_json(utilisateur) FROM vision_gestion.comptes WHERE actif AND administrateur ORDER BY utilisateur LIMIT 1"))
        backup.exiger(isinstance(proprietaire,str) and re.fullmatch('[A-Za-z0-9_.-]{1,128}',proprietaire))
        ids=json.loads(sql('vision',"SELECT coalesce(json_agg(id),'[]') FROM (SELECT id FROM vision_items WHERE utilisateur="+"'"+proprietaire+"' ORDER BY id LIMIT 1) s"))
        backup.exiger(len(ids)==1)
        contenu=json.dumps({'type':'item','ids':ids}).encode()
        def fenetres(instant):
            # Propriétaire déjà validé ; instant ISO reparsé/canonique et IDs
            # issus de la base. Aucune valeur ou ligne personnelle journalisée.
            if any(type(i) is not int or not 0<i<2**63 for i in ids):raise ValueError('IDs restaurés inattendus')
            q="""BEGIN READ ONLY;
SELECT coalesce(json_object_agg(i.id,vision_fenetre(i.stabilite,
 coalesce((SELECT max(f.priorite) FROM vision_liens l JOIN vision_fiches f
   ON f.utilisateur=l.utilisateur AND f.id=l.fiche_id
   WHERE l.utilisateur=i.utilisateur AND l.item_id=i.id AND f.archive_a IS NULL),0),
 coalesce(pr.intervalle_jours,90),coalesce(pr.decalage,0),i.reference_a,
 '"""+instant+"""'::timestamptz)),'{}')
FROM vision_items i LEFT JOIN vision_profils pr ON pr.utilisateur=i.utilisateur
WHERE i.utilisateur='"""+proprietaire+"' AND i.id IN ("+','.join(map(str,ids))+'); COMMIT;'
            return json.loads(sql('vision',q))
        env={'PATH':os.environ['PATH'],'LANG':'C.UTF-8','PGHOST':str(isole),'PGUSER':'vision','PGDATABASE':'vision',
             'PGOPTIONS':'-c TimeZone=UTC -c DateStyle=ISO',
             'VISION_PSQL':str(wrapper),'VISION_DOCUMENT_ROOT':prepare['parametres']['documentVision'],'VISION_VERSION':'2.7.0',
             'MRJAM_LIBCRYPTO':str(outils/'openssl/lib/libcrypto.so.3'),
             'MRJAM_LIBPQ':str(outils/'postgresql/lib/libpq.so.5'),
             'MRJAM_LIBSQLITE':str(outils/'sqlite/lib/libsqlite3.so.0'),
             'MRJAM_INGRESS_UID':'0','MRJAM_SOCKET':str(essais/'metier.sock'),
             'VISION_DSN':'host='+str(isole)+' user=vision dbname=vision',
             'MATHEVAL_DSN':'host='+str(isole)+' user=matheval_app dbname=matheval',
             'MATHEVAL_BANK_VERSION':prepare['parametres']['bankVersion'],'MATHEVAL_ORIGIN':'https://principiipetit.io'}
        with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
        env.update(IP='127.0.0.1',PORT=str(port))
        # Copies issues de la même sauvegarde restaurée, jamais leurs originaux.
        etats=essais/'etats';etats.mkdir(mode=0o700);os.chown(etats,user.pw_uid,user.pw_gid)
        noms={'cycle':'cycle/courriels.sqlite','admissions':'admission/admissions.sqlite',
              'admission-courriel':'admission/courriels.sqlite','fermetures':'fermeture/courriels.sqlite',
              'courriel':'courriel/file.sqlite'}
        projections={}
        def projection(path,definition=None):
            with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as c:
                if definition is None:
                    definition={t:[row[1] for row in c.execute('PRAGMA table_info("'+t.replace('"','""')+'")')]
                                for (t,) in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
                h={}
                for t,cols in definition.items():
                    q='SELECT '+','.join(backup.identifiant(col) for col in cols)+' FROM '+backup.identifiant(t)
                    rows=[json.dumps([{'blob':v.hex()} if isinstance(v,bytes) else v for v in row],ensure_ascii=False) for row in c.execute(q)]
                    h[t]=sorted(rows)
                return definition,h
        for nom,relatif in noms.items():
            cible=etats/relatif;cible.parent.mkdir(mode=0o700,exist_ok=True)
            os.chown(cible.parent,user.pw_uid,user.pw_gid)
            if nom in copies_etats:
                shutil.copyfile(copies_etats[nom],cible);cible.chmod(0o600);os.chown(cible,user.pw_uid,user.pw_gid)
                projections[relatif]=projection(cible)
        recipient=backup.nix('(import <nixpkgs/nixos/lib/eval-config.nix> { system="x86_64-linux"; modules=[ /etc/nixos/configuration.nix ]; }).config.services.vision.backupRecipient')
        testenv=dict(env,MRJAM_ETATS_ISOLES=str(etats),MRJAM_AGE_RECIPIENT=recipient,AGE=str(outils/'age/bin/age'))
        source_test=essais/'sources';source_test.mkdir(mode=0o700)
        chemins={'vps':'vps','vision':'vision','matheval':'M-moire'}
        for name in list(cert['qualification']['sources_lisp_sha256'])+['vps/tests/restauration-etats.lisp',
                'vps/assemblage/oidc/charger-dependances.lisp']:
            composant,relatif=name.split('/',1);cible=source_test/chemins[composant]/relatif
            cible.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(d/'payload'/name,cible)
        for p in (source_test,*source_test.rglob('*')):
            os.chown(p,user.pw_uid,user.pw_gid);p.chmod(0o700 if p.is_dir() else 0o600)
        backup.commande(['runuser','-u','vision','--','env','-i',*[k+'='+v for k,v in testenv.items()],
                         outils/'sbcl/bin/sbcl','--script',source_test/'vps/tests/restauration-etats.lisp'],timeout=120)
        for relatif,(definition,lignes) in projections.items():
            backup.exiger(projection(etats/relatif,definition)==(definition,lignes))
        def lire_ancien():
            req=urllib.request.Request('http://127.0.0.1:'+str(port)+'/api/v1/lire',data=contenu,
                headers={'Content-Type':'application/json','X-Vision-Authenticated':'1','X-Mrj-User':proprietaire})
            with urllib.request.urlopen(req,timeout=12) as r:
                backup.exiger(r.status==200);return json.loads(r.read(2*1024*1024))
        http=module('mrjam_http',ROOT/'tests/serveur-artefact.py')
        def lire_commun():
            extra=('X-Vision-Authenticated: 1\r\nX-Mrj-User: '+proprietaire+'\r\n').encode()
            code,_,raw=http.requete(essais/'metier.sock',http.http('POST','/api/v1/lire',service='vision',corps=contenu,extra=extra))
            backup.exiger(code==200);return json.loads(raw)
        def essai(binary,lecture,unix=False,operation=None):
            journal=(isole/('commun-prive.log' if unix else 'retour-prive.log')).open('wb')
            p=subprocess.Popen(['runuser','-u','vision','--','env','-i',*[k+'='+v for k,v in env.items()],str(binary)],stdout=journal,stderr=journal,start_new_session=True)
            try:
                for _ in range(100):
                    backup.exiger(p.poll() is None)
                    try:valeur=lecture()
                    except (OSError,ValueError):time.sleep(.1)
                    else:break
                else:raise ValueError('Exécutable restauré indisponible')
                # Les écritures sur la copie ne sont jamais rejouées pour
                # attendre le démarrage ou masquer un échec.
                return operation(valeur) if operation else valeur
            finally:
                os.killpg(p.pid,signal.SIGTERM)
                try:p.wait(timeout=12)
                except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait();raise ValueError('Arrêt non borné')
                journal.close();(essais/'metier.sock').unlink(missing_ok=True)
        old=essai(ancien,lire_ancien);new=essai(image,lire_commun,True)
        backup.exiger(comparer_lectures(old,new,fenetres) and [o['id'] for o in new['objets']]==ids)
        original=new['objets'][0]['contenu']
        def payload(obj,texte):return json.dumps({'id':obj['id'],'version':obj['version'],
            'contenu':texte,'cle':str(uuid.uuid4()),'emise_a':datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00','Z')}).encode()
        def modifier_commun(lu):
            data=payload(lu['objets'][0],original+'\n\nContrôle isolé de retour applicatif.')
            extra=('X-Vision-Authenticated: 1\r\nX-Mrj-User: '+proprietaire+'\r\n').encode()
            code,_,_=http.requete(essais/'metier.sock',http.http('POST','/api/v1/enregistrer_item',service='vision',corps=data,extra=extra))
            backup.exiger(code==200);return lire_commun()
        modifie=essai(image,lire_commun,True,modifier_commun)
        backup.exiger(comparer_lectures(essai(ancien,lire_ancien),modifie,fenetres))
        def modifier_ancien(lu):
            req=urllib.request.Request('http://127.0.0.1:'+str(port)+'/api/v1/enregistrer_item',data=payload(lu['objets'][0],original),
                headers={'Content-Type':'application/json','X-Vision-Authenticated':'1','X-Mrj-User':proprietaire})
            with urllib.request.urlopen(req,timeout=12) as r:backup.exiger(r.status==200);r.read(2*1024*1024)
            return lire_ancien()
        retour=essai(ancien,lire_ancien,operation=modifier_ancien)
        backup.exiger(retour['objets'][0]['contenu']==original)
        # Redémarrer la même image ; seules lectures, aucun faux objet ajouté.
        backup.exiger(comparer_lectures(essai(image,lire_commun,True),retour,fenetres))
        return {'acl_vision_30_matheval_6':True,'migration_26_sur_copie':True,
          'migration_27_rls_sur_copie':True,
          'fenetres_verifiees_aux_instants_de_lecture':True,
          'contenus_metier_preserves':True,'lectures_ancien_et_commun_identiques':True,
          'redemarrage_commun':True,'retour_lecture_qualifie':True,
          'retour_code_sans_restaurer_production':True,'sqlite_colonnes_et_messages_historiques_preserves':True,
          'ecritures_sur_copie_communes_lues_par_ancien':True,
          'ecritures_sur_copie_ancien_lues_apres_redemarrage_commun':True,
          'retour_operations_ecriture_restant':False,
          'idp_smtp_non_contactes':True,'donnees_synthetiques_en_production':False}
    activer=module('mrjam_reprise_etats',ROOT/'scripts/monolithe-activer.py')
    reprise=activer.reprise_certifiee(d,prepare,cert)
    sqlite_reprise={};registres_reprise={}
    if reprise:
        sources=activer.sources_durables(True)
        aliases={'cycle-courriels':'cycle','admissions':'admissions','admission-courriels':'admission-courriel',
                 'fermeture-courriels':'fermetures','courriel':'courriel',
                 'effacements':'effacements','effacements-cycle':'effacements-cycle',
                 'effacements-fermeture':'effacements-communs'}
        for n,p in sources.items():
            cible=activer.ETAT_METIER/activer.DESTINATIONS[n]
            collection=sqlite_reprise if cible.suffix=='.sqlite' else registres_reprise
            if p!=Path(stage.ETATS[n]) and p.exists():collection[aliases[n]]=str(p)
            if cible.exists():collection['avant-reprise-'+aliases[n]]=str(cible)
    rapport=backup.main(revision,qualifier=qualifier,sqlite_reprise=sqlite_reprise,registres_reprise=registres_reprise)
    rapport['etats_communs_precedents_chiffres']=bool(reprise)
    (d/'restauration.json').write_text(json.dumps(rapport,ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':
    try:
        os.umask(0o077)
        with open('/root/mrjam-assemblage.lock','a') as f:
            fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);main(sys.argv[1])
    except Exception:
        if len(sys.argv)==2 and re.fullmatch('[a-f0-9]{40}',sys.argv[1]):
            d=Path('/root/mrjam-assemblages')/sys.argv[1]
            if d.is_dir() and not d.is_symlink():(d/'erreur-restauration-privee.log').write_text(traceback.format_exc())
        print('Restauration isolée refusée ; diagnostic privé sur le VPS.',file=sys.stderr);sys.exit(1)
