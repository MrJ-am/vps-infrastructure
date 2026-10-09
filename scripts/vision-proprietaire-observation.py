"""Projection des seules preuves pwd/otp du sujet initial, sans contenu personnel."""
import json
import os
import re
import subprocess
import time

UUID=r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}'


def sql_prive(runuser,psql,sql):
    env={k:v for k,v in os.environ.items() if not k.startswith('PG')};env['PGCONNECT_TIMEOUT']='5'
    r=subprocess.run([runuser,'-u','postgres','--',psql,'-XAtq','-v','ON_ERROR_STOP=1',
        '-h','/run/mrjam-amorcage-postgresql','-U','postgres','-d','mrjam_identite','-f','-'],
        env=env,input=("BEGIN READ ONLY; SET LOCAL statement_timeout='5s'; SET LOCAL lock_timeout='2s';\n"+sql+'; COMMIT;').encode(),
        capture_output=True,timeout=10)
    if r.returncode or len(r.stdout)>65536:raise ValueError('Observation privée indisponible')
    return json.loads(r.stdout)


def executions(api,runuser,psql):
    sql="SELECT json_object_agg(alias,config) FROM (SELECT c.alias,json_object_agg(e.name,e.value) AS config FROM authenticator_config c JOIN authenticator_config_entry e ON e.authenticator_id=c.id WHERE c.realm_id=(SELECT id FROM realm WHERE name='mrjam') AND c.alias IN ('mrjam-mot-de-passe','mrjam-second-facteur') AND e.name IN ('default.reference.value','default.reference.maxAge') GROUP BY c.alias) q"
    configurations=sql_prive(runuser,psql,sql)
    methodes={'auth-username-password-form':('mrjam-mot-de-passe','pwd'),'auth-otp-form':('mrjam-second-facteur','otp')}
    resultats={}
    for e in api('/admin/realms/mrjam/authentication/flows/mrjam-browser/executions'):
        if e.get('providerId') not in methodes:continue
        alias,methode=methodes[e['providerId']]
        if e.get('requirement')!='REQUIRED' or not re.fullmatch(UUID,e.get('id','')) or not re.fullmatch(UUID,e.get('authenticationConfig','')):raise ValueError('Flux initial différent')
        cfg=api('/admin/realms/mrjam/authentication/config/'+e['authenticationConfig'])
        if cfg.get('alias')!=alias or configurations.get(alias)!={'default.reference.value':methode,'default.reference.maxAge':'300'}:raise ValueError('Preuve de méthode différente')
        resultats.setdefault(methode,[]).append(e['id'])
    if set(resultats)!={'pwd','otp'} or any(len(v)!=1 for v in resultats.values()):raise ValueError('Méthodes initiales différentes')
    return resultats


def sessions(runuser,psql,sujet):
    if not isinstance(sujet,str) or not re.fullmatch(UUID,sujet):raise ValueError('Sujet initial différent')
    sql="SELECT COALESCE(json_agg(preuve),'[]'::json) FROM (SELECT json_build_object('authMethod', data::json->'authMethod','notes',json_build_object('AUTH_TIME',data::json->'notes'->'AUTH_TIME','authenticators-completed',data::json->'notes'->'authenticators-completed')) AS preuve FROM offline_user_session WHERE user_id='"+sujet+"' AND realm_id=(SELECT id FROM realm WHERE name='mrjam') AND offline_flag='0' LIMIT 32) q"
    return sql_prive(runuser,psql,sql)
