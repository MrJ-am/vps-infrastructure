"""Inventaire fermé des tables, RLS et capacités SQL effectives, sans lire de données.

Le callback reçoit exclusivement des requêtes de métadonnées et renvoie du JSON.
La validation des prédicats RLS et de l'identité requiert aussi les tests Alice/Bob.
"""
import json
from pathlib import Path

RACINE=Path(__file__).resolve().parents[1]
OPERATIONS=('SELECT','INSERT','UPDATE','DELETE','TRUNCATE','REFERENCES','TRIGGER')
ROLES_SQL="""SELECT coalesce(json_agg(json_build_object('nom',rolname,'super',rolsuper,
 'bypass',rolbypassrls,'creer_role',rolcreaterole,'creer_base',rolcreatedb,
 'replication',rolreplication,'membre_proprietaire',EXISTS(SELECT FROM pg_roles p WHERE pg_has_role(r.oid,p.oid,'MEMBER')
 AND (p.rolsuper OR p.rolbypassrls OR p.rolcreaterole OR p.rolcreatedb OR p.rolreplication OR p.oid IN
  (SELECT c.relowner FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname IN ('public','vision_gestion')))))
 ORDER BY rolname),'[]'::json) FROM pg_roles r WHERE rolname IN ({roles})"""
TABLES_SQL="""SELECT coalesce(json_agg(json_build_object('table',n.nspname||'.'||c.relname,
 'rls',c.relrowsecurity,'force_rls',c.relforcerowsecurity,'proprietaire',pg_get_userbyid(c.relowner),
 'colonne_utilisateur',EXISTS(SELECT FROM pg_attribute WHERE attrelid=c.oid AND attname='utilisateur' AND NOT attisdropped),
 'politiques',(SELECT count(*) FROM pg_policy WHERE polrelid=c.oid),
 'droits_colonnes',EXISTS(SELECT FROM pg_roles r WHERE r.rolname IN ({roles}) AND EXISTS
  (SELECT FROM unnest(ARRAY['SELECT','INSERT','UPDATE','REFERENCES']) a(op)
   WHERE has_any_column_privilege(r.oid,c.oid,op) AND NOT has_table_privilege(r.oid,c.oid,op))),
 'droits_directs',(SELECT json_object_agg(r.rolname,
  (SELECT coalesce(json_agg(op ORDER BY ordre),'[]'::json) FROM unnest(ARRAY[{operations}]) WITH ORDINALITY a(op,ordre)
   WHERE has_table_privilege(r.oid,c.oid,op))) FROM pg_roles r WHERE r.rolname IN ({roles})))
 ORDER BY n.nspname,c.relname),'[]'::json)
 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
 WHERE c.relkind IN ('r','p') AND n.nspname IN ('public','vision_gestion')"""

def valider(composant,tables,roles,inventaire):
    attendus=inventaire[composant]
    observes={t['table']:t for t in tables}
    if len(observes)!=len(tables) or set(observes)!=set(attendus):
        raise ValueError('Tables non classées ou absentes : '+str(sorted(set(observes)^set(attendus))))
    requis=set().union(*(set(t['droits_directs']) for t in attendus.values()))
    if {r['nom'] for r in roles}!=requis:raise ValueError('Rôles applicatifs absents ou inattendus')
    for r in roles:
        if any(r[k] for k in ('super','bypass','creer_role','creer_base','replication','membre_proprietaire')):
            raise ValueError('Rôle SQL privilégié : '+r['nom'])
    for nom,a in attendus.items():
        o=observes[nom]
        if not a.get('classe'):raise ValueError('Classe absente : '+nom)
        for k in ('rls','force_rls','colonne_utilisateur'):
            if o[k]!=a[k]:raise ValueError('Contrat SQL divergent : '+nom+' '+k)
        if 'proprietaire' in a and o['proprietaire']!=a['proprietaire']:raise ValueError('Propriétaire divergent : '+nom)
        if o['proprietaire'] in requis|set(a.get('proprietaire_interdit',[])):raise ValueError('Rôle applicatif propriétaire : '+nom)
        if a['rls'] and not o['politiques']:raise ValueError('RLS sans politique : '+nom)
        if o['droits_colonnes']:raise ValueError('Droits de colonne supplémentaires : '+nom)
        if o['droits_directs']!=a['droits_directs']:raise ValueError('Droits directs divergents : '+nom)

def verifier(composant,requete):
    inventaire=json.loads((RACINE/'assemblage/tables-privees.json').read_text())
    roles=set().union(*(set(t['droits_directs']) for t in inventaire[composant].values()))
    # Les valeurs proviennent du contrat versionné ; aucune entrée HTTP/DSN.
    if any(not r.replace('_','').isalnum() for r in roles):raise ValueError('Nom de rôle invalide')
    liste=','.join("'"+r+"'" for r in sorted(roles))
    tables=json.loads(requete(TABLES_SQL.format(roles=liste,operations=','.join("'"+o+"'" for o in OPERATIONS))))
    comptes=json.loads(requete(ROLES_SQL.format(roles=liste)))
    valider(composant,tables,comptes,inventaire)
    print(f'{composant}: {len(tables)} tables classées, RLS/ACL et rôles effectifs vérifiés ; aucune ligne métier lue.')
