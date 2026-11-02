#!/usr/bin/env python3
"""Read-only fixed inherited SQL catalogue predicates; no application data.
No SQL function from application schemas is called. No business read/write.
"""
import json
import os
import resource
import signal
import subprocess
import sys

PREVIOUS='/nix/store/jn9rf2fgk2y6dbhdnjwkmfww3pchkyb9-nixos-system-nixos-26.05.8639.c5c4a43b0e80'
QUERIES={'cycle_fixed_capabilities': "SELECT\n      (SELECT NOT rolsuper AND NOT rolbypassrls AND NOT rolcreaterole AND NOT rolcreatedb FROM pg_roles WHERE rolname='vision_cycle')\n      AND NOT has_schema_privilege('vision_cycle','vision_gestion','CREATE')\n      AND NOT has_schema_privilege('vision_cycle','public','CREATE')\n      AND (SELECT count(*)>=14 AND bool_and(NOT has_table_privilege('vision_cycle',c.oid,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')\n        AND NOT pg_has_role('vision_cycle',c.relowner,'MEMBER')) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace\n        WHERE n.nspname='public' AND c.relname LIKE 'vision_%' AND c.relkind='r')\n      AND (SELECT count(*)=cardinality(ARRAY['vision_gestion.preavis_a_traiter()','vision_gestion.constater_preavis(uuid,text)','vision_gestion.engager_effacement(text,uuid)','vision_gestion.effacer_cycle(text,text,uuid)']::text[]) AND bool_and(p.prosecdef AND NOT r.rolcanlogin\n        AND NOT r.rolsuper AND NOT r.rolbypassrls AND NOT pg_has_role('vision_cycle',p.proowner,'MEMBER')\n        AND has_function_privilege('vision_cycle',p.oid,'EXECUTE'))\n        FROM unnest(ARRAY['vision_gestion.preavis_a_traiter()','vision_gestion.constater_preavis(uuid,text)','vision_gestion.engager_effacement(text,uuid)','vision_gestion.effacer_cycle(text,text,uuid)']::text[]) f(nom) JOIN pg_proc p ON p.oid=to_regprocedure(f.nom) JOIN pg_roles r ON r.oid=p.proowner)\n      AND NOT EXISTS(SELECT FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace\n        WHERE n.nspname='vision_gestion' AND has_function_privilege('vision_cycle',p.oid,'EXECUTE')\n        AND NOT p.oid=ANY(ARRAY(SELECT to_regprocedure(f)::oid FROM unnest(ARRAY['vision_gestion.preavis_a_traiter()','vision_gestion.constater_preavis(uuid,text)','vision_gestion.engager_effacement(text,uuid)','vision_gestion.effacer_cycle(text,text,uuid)']::text[]) f)))", 'vision_row_security': "SELECT (SELECT NOT rolsuper AND NOT rolbypassrls FROM pg_roles WHERE rolname='vision')\n  AND count(*) = 14\n  AND bool_and(c.relrowsecurity AND c.relforcerowsecurity\n    AND NOT pg_has_role('vision', c.relowner, 'MEMBER')\n    AND (SELECT count(*)=1 AND bool_and(p.polname='proprietaire' AND p.polcmd='*'\n      AND p.polpermissive AND p.polroles=ARRAY[0::oid]\n      AND pg_get_expr(p.polqual,p.polrelid) = '(utilisateur = current_setting(''vision.utilisateur''::text, true))'\n      AND pg_get_expr(p.polwithcheck,p.polrelid) = '(utilisateur = current_setting(''vision.utilisateur''::text, true))')\n      FROM pg_policy p WHERE p.polrelid=c.oid))\nFROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace\nWHERE n.nspname='public' AND c.relkind='r' AND c.relname IN (\n 'vision_contextes','vision_embeddings','vision_episodes','vision_fiches',\n 'vision_items','vision_journal','vision_liens','vision_migrations_metier',\n 'vision_observations','vision_preparations_items','vision_profils',\n 'vision_recherches','vision_requetes','vision_seances')", 'vision_administration_capabilities': "SELECT (SELECT NOT rolsuper AND NOT rolbypassrls FROM pg_roles WHERE rolname='vision_administration')\n AND has_function_privilege('vision_administration','vision_gestion.administrer(text,text,jsonb)','EXECUTE')\n AND NOT has_function_privilege('vision_administration','vision_gestion.effacer(text,text)','EXECUTE')\n AND NOT has_function_privilege('vision_administration','vision_gestion.activer(text,text,text,text,text)','EXECUTE')\n AND EXISTS(SELECT FROM pg_proc p JOIN pg_roles o ON p.proowner=o.oid\n   WHERE p.oid='vision_gestion.administrer(text,text,jsonb)'::regprocedure\n     AND p.prosecdef AND NOT o.rolcanlogin AND NOT o.rolsuper AND NOT o.rolbypassrls\n     AND NOT pg_has_role('vision_administration',o.oid,'MEMBER'))\n AND (SELECT count(*)>=14 AND bool_and(NOT has_table_privilege('vision_administration',c.oid,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE'))\n   FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace\n   WHERE n.nspname='public' AND c.relkind='r' AND c.relname LIKE 'vision_%')", 'audition_row_security': "SELECT count(*)=7 AND bool_and(NOT pg_has_role('audition_app',c.relowner,'MEMBER')) AND bool_and(c.relrowsecurity) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='audition' AND c.relname IN ('administrateurs','groupes','membres','objets','versions','requetes','audit')"}

def parse(raw):
    value=raw.strip()
    if value not in ('t','f'):raise ValueError()
    return {'observed':True,'accepted':value=='t'}

def collect():
    values={}
    for name,query in QUERIES.items():
        sql="BEGIN READ ONLY; SET LOCAL statement_timeout='5s'; SET LOCAL lock_timeout='1s'; SET LOCAL search_path=pg_catalog; SELECT coalesce(("+query+"),false); ROLLBACK;"
        try:
            process=subprocess.run([PREVIOUS+'/sw/bin/runuser','-u','postgres','--',PREVIOUS+'/sw/bin/psql',
                '-X','-w','-qAt','-h','/run/postgresql','-p','5432','-d','vision','-v','ON_ERROR_STOP=1','-c',sql],
                stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=10,check=False,
                env={'PATH':PREVIOUS+'/sw/bin','LANG':'C','LC_ALL':'C','PGPASSFILE':'/dev/null',
                     'PGSERVICEFILE':'/dev/null','PGCONNECT_TIMEOUT':'5',
                     'PGOPTIONS':'-c default_transaction_read_only=on -c statement_timeout=5000'})
            if process.returncode or len(process.stdout)>64:raise ValueError()
            values[name]=parse(process.stdout.decode('ascii','strict'))
        except Exception:values[name]={'observed':False}
    return {'schema_version':1,'code':'LIFECYCLE_CATALOG_OBSERVED','checks':values,
            'read_only':True,'application_rows_read':False,'secret_content_read':False,
            'journals_read':False,'application_functions_called':False,'mutation_performed':False,
            'schema_migration_values_checked':False,'application_readiness_proved':False,
            'all_catalog_checks_accepted':all(v.get('accepted') is True for v in values.values())}

def main():
    if len(sys.argv)!=1 or os.geteuid()!=0 or os.path.realpath('/run/current-system')!=PREVIOUS:return 64
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    resource.setrlimit(resource.RLIMIT_AS,(256*1024**2,256*1024**2))
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError()))
    signal.alarm(45)
    try:result=collect()
    except Exception:result={'schema_version':1,'code':'LIFECYCLE_CATALOG_UNAVAILABLE','private_values_exported':False}
    finally:signal.alarm(0)
    print(json.dumps(result,sort_keys=True,separators=(',',':')))
    return 0 if all(v.get('observed') for v in result.get('checks',{'unavailable':{}}).values()) else 1

if __name__=='__main__':raise SystemExit(main())
