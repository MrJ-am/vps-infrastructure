"""Réparer la dérive RLS réelle dans un PostgreSQL jetable, sans données réelles."""
import json
import copy
import importlib.util
import os
from pathlib import Path
import subprocess
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
IMAGE='mirror.gcr.io/pgvector/pgvector@sha256:40b404964359299eefdd5f8518facf1886c562848cf4de13b6eaf91cb70c2b87'


def verifier():
    source=Path(os.environ.get('MRJAM_ATELIER',ROOT.parent))/'vision'
    catalogue=json.loads((ROOT/'assemblage/tables-privees.json').read_text())['vision']
    privees=sorted(t for t,a in catalogue.items() if t.startswith('public.') and a['rls'])
    assert len(privees)==14
    nom='mrjam-rls-'+uuid.uuid4().hex[:12]
    def docker(*args,input=None,check=True):
        return subprocess.run(['docker',*args],input=input,text=True,capture_output=True,check=check)
    def sql(texte,check=True):
        return docker('exec','-i',nom,'psql','-XqAt','-U','postgres','-d','vision_rls_test',
                      '--set=ON_ERROR_STOP=1','--file=-',input=texte,check=check)
    def lire(texte):return json.loads(sql(texte).stdout)
    def protections():
        return lire("SELECT json_object_agg(n.nspname||'.'||c.relname,json_build_array(relrowsecurity,relforcerowsecurity)) "
                    "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                    "WHERE relkind='r' AND n.nspname IN ('public','vision_gestion')")
    def empreintes():
        champs=["'"+t+"',(SELECT md5(coalesce(jsonb_agg(to_jsonb(r) ORDER BY to_jsonb(r)),'[]'::jsonb)::text) FROM "+t+' r)'
                for t in catalogue if t!='public.vision_schema_migrations']
        return lire('SELECT json_build_object('+','.join(champs)+')')
    docker('run','--detach','--name',nom,'--network','none','--env','POSTGRES_HOST_AUTH_METHOD=trust',
           '--env','POSTGRES_DB=vision_rls_test',IMAGE)
    try:
        for _ in range(100):
            r=docker('exec',nom,'pg_isready','-h','127.0.0.1','-U','postgres',check=False)
            if r.returncode==0:break
            time.sleep(.1)
        else:raise AssertionError('PostgreSQL isolé indisponible')
        sql('CREATE EXTENSION vector;\n'+''.join(p.read_text()+'\n' for p in sorted((source/'migrations').glob('*.sql'))
                                                if int(p.name.split('_')[0])<=26))
        sql((source/'scripts/roles.sql').read_text())
        sql("""
UPDATE vision_gestion.configuration SET inscriptions_ouvertes=true,responsable='Fixture',contact='rls@example.test',pays_hebergement='Test',notice_version='rls';
INSERT INTO vision_gestion.comptes(utilisateur,affichage) VALUES('alice','Alice'),('bob','Bob');
INSERT INTO vision_profils(utilisateur) VALUES('alice'),('bob');
INSERT INTO vision_fiches(utilisateur,titre,contenu) VALUES('alice','Fiche Alice','Contenu Alice'),('bob','Fiche Bob','Contenu Bob');
INSERT INTO vision_items(utilisateur,titre,contenu,objectifs,sens) VALUES('alice','Item Alice','Contenu Alice',ARRAY['definition'],ARRAY['rappel']),('bob','Item Bob','Contenu Bob',ARRAY['definition'],ARRAY['rappel']);
UPDATE vision_items SET reference_a='2026-01-01T00:00:00Z',origine_reference='declaree' WHERE utilisateur='alice';
INSERT INTO vision_liens(utilisateur,fiche_id,item_id) VALUES('alice',1,1),('bob',2,2);
INSERT INTO vision_observations(utilisateur,item_id,texte,source,evenement_a) VALUES('alice',1,'Observation datée','explicite','2026-01-02T03:04:05Z');
INSERT INTO vision_seances(utilisateur,fiche_id,items) VALUES('alice',1,'[{"id":1}]');
""")
        originaux=empreintes();normal=protections()
        assert all(normal[t]==[True,True] for t in privees)
        spec=importlib.util.spec_from_file_location('tables_roles_rls',ROOT/'scripts/verifier-tables.py')
        controleur=importlib.util.module_from_spec(spec);spec.loader.exec_module(controleur)
        roles_query=controleur.ROLES_SQL.format(roles="'vision'")
        definition_vue=sql("SELECT pg_get_viewdef('public.vision_browser_sheets'::regclass)").stdout
        # Dérive historique : la vue appartient à l'ancien rôle applicatif.
        # La restauration --no-owner ne reproduisait pas cette propriété.
        sql('ALTER VIEW public.vision_browser_sheets OWNER TO vision; GRANT SELECT ON public.vision_browser_sheets TO vision')
        assert lire(roles_query)[0]['membre_proprietaire'] is True
        sql((source/'scripts/roles.sql').read_text())
        sql((source/'scripts/roles.sql').read_text())
        assert not any(v for k,v in lire(roles_query)[0].items() if k!='nom')
        assert sql("SELECT pg_get_userbyid(relowner) FROM pg_class WHERE oid='public.vision_browser_sheets'::regclass").stdout.strip()=='vision_migration'
        assert sql("SELECT pg_get_viewdef('public.vision_browser_sheets'::regclass)").stdout==definition_vue
        assert empreintes()==originaux and protections()==normal
        e=sql('BEGIN; SET LOCAL ROLE vision; SELECT count(*) FROM public.vision_browser_sheets; ROLLBACK;',check=False)
        assert e.returncode!=0 and 'permission denied' in e.stderr
        # Reproduire les métadonnées effectivement constatées sur le VPS.
        sql('\n'.join('ALTER TABLE '+t+' DISABLE ROW LEVEL SECURITY; ALTER TABLE '+t+' NO FORCE ROW LEVEL SECURITY;' for t in privees))
        derive=protections()
        assert all(derive[t]==[False,False] for t in privees)
        migration=(source/'migrations/027_retablir_rls.sql').read_text()
        # L'erreur tardive doit annuler les changements des tables précédentes.
        sql('CREATE POLICY inattendue ON public.vision_seances USING(true)')
        e=sql(migration,check=False)
        assert e.returncode!=0 and 'rls_politique_inattendue: vision_seances' in e.stderr
        assert protections()==derive and empreintes()==originaux
        assert lire('SELECT to_json(max(version)) FROM vision_schema_migrations')==26
        sql('DROP POLICY inattendue ON public.vision_seances; ALTER POLICY proprietaire ON public.vision_contextes USING(true) WITH CHECK(true)')
        sql(migration);sql(migration)
        assert protections()==normal and empreintes()==originaux
        assert lire('SELECT to_json(count(*)) FROM vision_seances WHERE etat=\'ouverte\'')==1
        assert lire('SELECT to_json(count(*)) FROM vision_schema_migrations WHERE version=27')==1
        # Tester les prédicats, pas seulement le nombre de politiques.
        def alice(q):return sql("BEGIN; SET LOCAL ROLE vision; SELECT set_config('vision.utilisateur','alice',true); "+q+'; ROLLBACK;')
        assert alice("SELECT json_agg(utilisateur ORDER BY utilisateur) FROM vision_fiches").stdout.splitlines()[-1]=='["alice"]'
        assert alice("WITH changes AS (UPDATE vision_fiches SET titre='Vol' WHERE utilisateur='bob' RETURNING *) SELECT count(*) FROM changes").stdout.splitlines()[-1]=='0'
        e=sql("BEGIN; SET LOCAL ROLE vision; SELECT set_config('vision.utilisateur','alice',true); INSERT INTO vision_contextes(utilisateur,conversation) VALUES('bob','interdite'); ROLLBACK;",check=False)
        assert e.returncode!=0 and 'row-level security' in e.stderr
        e=sql("BEGIN; SET LOCAL ROLE vision; SELECT set_config('vision.utilisateur','alice',true); INSERT INTO vision_liens(utilisateur,fiche_id,item_id) VALUES('alice',1,2); ROLLBACK;",check=False)
        assert e.returncode!=0 and 'foreign key constraint' in e.stderr
        # Une nouvelle transaction ne conserve pas l'identité précédente.
        assert sql('BEGIN; SET LOCAL ROLE vision; SELECT count(*) FROM vision_fiches; ROLLBACK;').stdout.strip()=='0'
        assert empreintes()==originaux
        # Deux vrais instants SQL : les réponses complètes/urgences diffèrent,
        # chaque fenêtre reste vérifiée par la fonction métier inchangée.
        spec=importlib.util.spec_from_file_location('restauration_lectures',ROOT/'scripts/monolithe-restaurer.py')
        restauration=importlib.util.module_from_spec(spec);spec.loader.exec_module(restauration)
        a=lire("SELECT vision_lire('alice','{\"type\":\"item\",\"ids\":[1]}')")
        b=lire("SELECT vision_lire('alice','{\"type\":\"item\",\"ids\":[1]}')")
        def fenetres(instant):
            return lire("SELECT json_object_agg(id,vision_fenetre(stabilite,0,90,0,reference_a,'"+instant+"'::timestamptz)) FROM vision_items WHERE utilisateur='alice' AND id=1")
        assert a!=b and a['objets'][0]['fenetre']['urgence']!=b['objets'][0]['fenetre']['urgence']
        assert restauration.comparer_lectures(a,b,fenetres)
        for champ,valeur in [('contenu','Altéré'),('modifie_a','2025-01-01T00:00:00Z'),('stabilite',127),('reference_a',None)]:
            c=copy.deepcopy(b);c['objets'][0][champ]=valeur
            assert not restauration.comparer_lectures(a,c,fenetres)
        c=copy.deepcopy(b);c['politique']['version']+=1
        assert not restauration.comparer_lectures(a,c,fenetres)
        for champ,valeur in [('urgence',999),('etat','avant_fenetre'),('centre','2025-01-01T00:00:00Z')]:
            c=copy.deepcopy(b);c['objets'][0]['fenetre'][champ]=valeur
            try:restauration.comparer_lectures(a,c,fenetres)
            except ValueError:pass
            else:raise AssertionError('Fenêtre altérée acceptée : '+champ)
        c=copy.deepcopy(b);c['maintenant']='sans-fuseau'
        try:restauration.comparer_lectures(a,c,fenetres)
        except ValueError:pass
        else:raise AssertionError('Instant invalide accepté')
        print('RLS : dérive des 14 tables réparée, refus atomique, idempotence, données/observations/séance ouverte inchangées, isolation Alice/Bob, lien interpropriétaires refusé et transaction sans identité vérifiés.')
        print('Lectures : deux instants/urgences SQL réels, toutes données/dates/politiques comparées ; fenêtres recalculées et altérations refusées sans modification du modèle.')
    finally:docker('rm','--force',nom)


if __name__=='__main__':verifier()
