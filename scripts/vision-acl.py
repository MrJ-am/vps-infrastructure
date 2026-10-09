"""Relever puis préparer le retour ciblé des droits Vision sans restaurer les données.

Le relevé reste privé. Le retour antérieur à l'ouverture refuse tout nouveau
compte, admission en cours ou inscription ouverte. Il ne retire aucun contenu,
aucune migration et aucun rôle. L'arrêt des services et le retour NixOS sont
des étapes opérateur distinctes.
"""
import json

ROLES = ('vision', 'vision_administration', 'vision_identite', 'vision_cycle', 'vision_admission', 'vision_fermeture')


def identifiant(v):
    return '"' + v.replace('"', '""') + '"'


def litteral(v):
    return "'" + v.replace("'", "''") + "'"


def relever(sql):
    # Les adresses, mots de passe, condensats d'identifiants et contenus ne sont
    # jamais lus. Les identifiants propriétaires restent dans le dossier root.
    def lire(q):
        return json.loads(sql(q))
    proprietaires = lire("SELECT coalesce(json_agg(DISTINCT utilisateur),'[]') FROM public.vision_profils")
    if len(proprietaires) > 1:
        raise ValueError('Retour historique interdit : plusieurs propriétaires')
    colonnes = lire("SELECT count(*) FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relname LIKE 'vision_%' AND a.attacl IS NOT NULL")
    if colonnes:
        raise ValueError('Privilèges de colonnes à traiter explicitement')
    objets = lire("""
WITH objets AS (
 SELECT 'DATABASE' type, quote_ident(datname) nom, datdba owner, datacl acl, 'd'::"char" genre,
   false rls,false force_rls FROM pg_database WHERE datname=current_database()
 UNION ALL SELECT 'SCHEMA',quote_ident(nspname),nspowner,nspacl,'n'::"char",false,false
   FROM pg_namespace WHERE nspname='public'
 UNION ALL SELECT CASE c.relkind WHEN 'S' THEN 'SEQUENCE' WHEN 'v' THEN 'VIEW'
   WHEN 'm' THEN 'MATERIALIZED VIEW' ELSE 'TABLE' END,
   format('%I.%I',n.nspname,c.relname),c.relowner,c.relacl,
   CASE WHEN c.relkind='S' THEN 's'::"char" ELSE 'r'::"char" END,c.relrowsecurity,c.relforcerowsecurity
   FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
   WHERE n.nspname='public' AND c.relname LIKE 'vision_%' AND c.relkind IN ('r','p','S','v','m')
 UNION ALL SELECT 'FUNCTION',format('%I.%I(%s)',n.nspname,p.proname,pg_get_function_identity_arguments(p.oid)),
   p.proowner,p.proacl,'f'::"char",false,false FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
   WHERE n.nspname='public' AND p.proname LIKE 'vision_%' AND p.prokind='f'
)
SELECT coalesce(json_agg(json_build_object('type',o.type,'nom',o.nom,'owner',pg_get_userbyid(o.owner),
 'rls',o.rls,'force_rls',o.force_rls,'grants',(
 SELECT coalesce(json_agg(json_build_object('grantee',CASE WHEN a.grantee=0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END,
 'grantor',pg_get_userbyid(a.grantor),'privilege',a.privilege_type,'option',a.is_grantable)
 ORDER BY a.grantee,a.privilege_type),'[]') FROM aclexplode(coalesce(o.acl,acldefault(o.genre,o.owner))) a
 )) ORDER BY o.type,o.nom),'[]') FROM objets o
""")
    for o in objets:
        if any(g['grantor'] != o['owner'] for g in o['grants']):
            raise ValueError('Chaîne de délégation à traiter explicitement')
    role = lire("SELECT row_to_json(r) FROM (SELECT rolcanlogin,rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls,rolinherit FROM pg_roles WHERE rolname='vision') r")
    appartenances = lire("SELECT coalesce(json_agg(json_build_object('role',pg_get_userbyid(roleid),'member',pg_get_userbyid(member),'option',admin_option) ORDER BY roleid,member),'[]') FROM pg_auth_members WHERE roleid=(SELECT oid FROM pg_roles WHERE rolname='vision') OR member=(SELECT oid FROM pg_roles WHERE rolname='vision')")
    if appartenances:
        raise ValueError('Appartenance de rôle à traiter explicitement')
    return dict(version=1, proprietaires=proprietaires, objets=objets, role=role)


def retour(releve):
    if releve['version'] != 1 or len(releve['proprietaires']) > 1:
        raise ValueError('Relevé incompatible')
    autorises = ','.join(litteral(v) for v in releve['proprietaires']) or 'NULL'
    lignes = ["BEGIN;", "SET LOCAL lock_timeout='15s';", "SET LOCAL statement_timeout='5min';", """
DO $$ BEGIN
 IF to_regclass('vision_gestion.comptes') IS NOT NULL THEN
  LOCK TABLE vision_gestion.comptes IN ACCESS EXCLUSIVE MODE;
  PERFORM 1 FROM vision_gestion.configuration WHERE singleton FOR UPDATE;
  IF EXISTS(SELECT FROM vision_gestion.configuration WHERE inscriptions_ouvertes)
   OR EXISTS(SELECT FROM vision_gestion.admissions WHERE annulee_a IS NULL AND consommee_a IS NULL AND expire_a>now())
   OR EXISTS(SELECT FROM vision_gestion.comptes WHERE utilisateur NOT IN (""" + autorises + """)) THEN
   RAISE EXCEPTION 'Retour ancien incompatible : conserver une version multi-utilisateur et son isolation';
  END IF;
 END IF;
END $$;
"""]
    # NOT IN(NULL) ne représente pas l'ensemble vide dans SQL.
    if not releve['proprietaires']:
        lignes[-1] = lignes[-1].replace('WHERE utilisateur NOT IN (NULL)', '')
    # PostgreSQL refuse de changer le propriétaire d'une séquence liée avant
    # celui de sa table. Le relevé garde son ordre canonique pour comparaison.
    ordre = {'DATABASE': 0, 'SCHEMA': 1, 'TABLE': 2, 'VIEW': 3, 'MATERIALIZED VIEW': 4, 'SEQUENCE': 5, 'FUNCTION': 6}
    for o in sorted(releve['objets'], key=lambda o: (ordre[o['type']], o['nom'])):
        if o['type'] in ('TABLE', 'VIEW', 'MATERIALIZED VIEW'):
            lignes.append('LOCK TABLE ' + o['nom'] + ' IN ACCESS EXCLUSIVE MODE;')
        lignes.append('ALTER ' + o['type'] + ' ' + o['nom'] + ' OWNER TO ' + identifiant(o['owner']) + ';')
        if o['type'] == 'TABLE':
            lignes += ['ALTER TABLE ' + o['nom'] + (' ENABLE' if o['rls'] else ' DISABLE') + ' ROW LEVEL SECURITY;',
                'ALTER TABLE ' + o['nom'] + (' FORCE' if o['force_rls'] else ' NO FORCE') + ' ROW LEVEL SECURITY;']
        # Les nouveaux rôles sont présents après roles.sql ; le retour ne les
        # supprime pas et ne touche pas leurs usages dans d'autres bases.
        destinataires = {'PUBLIC', *ROLES, *(g['grantee'] for g in o['grants'])}
        roles = ','.join('PUBLIC' if r == 'PUBLIC' else identifiant(r) for r in sorted(destinataires))
        type_grant = 'TABLE' if o['type'] in ('VIEW', 'MATERIALIZED VIEW') else o['type']
        lignes.append('REVOKE ALL ON ' + type_grant + ' ' + o['nom'] + ' FROM ' + roles + ';')
        for g in o['grants']:
            r = 'PUBLIC' if g['grantee'] == 'PUBLIC' else identifiant(g['grantee'])
            lignes.append('GRANT ' + g['privilege'] + ' ON ' + type_grant + ' ' + o['nom'] + ' TO ' + r +
                (' WITH GRANT OPTION' if g['option'] else '') + ';')
    clauses = dict(rolcanlogin='LOGIN', rolsuper='SUPERUSER', rolcreatedb='CREATEDB', rolcreaterole='CREATEROLE',
        rolreplication='REPLICATION', rolbypassrls='BYPASSRLS', rolinherit='INHERIT')
    lignes.append('ALTER ROLE vision ' + ' '.join(('' if releve['role'][k] else 'NO') + v for k, v in clauses.items()) + ';')
    lignes.append('COMMIT;')
    return '\n'.join(lignes) + '\n'
