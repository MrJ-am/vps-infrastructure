"""Projection des seules preuves pwd/otp du sujet initial, sans contenu personnel."""
import json
import os
import re
import subprocess
import time

UUID=r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}'


class ObservationRefusee(ValueError):
    """Codes constants, sans réponse SQL/API dans les journaux publics."""
    pass


def exiger(condition, code):
    if not condition:raise ObservationRefusee(code)


def sql_prive(runuser,psql,sql):
    env={k:v for k,v in os.environ.items() if not k.startswith('PG')};env['PGCONNECT_TIMEOUT']='5'
    r=subprocess.run([runuser,'-u','postgres','--',psql,'-XAtq','-v','ON_ERROR_STOP=1',
        '-h','/run/mrjam-amorcage-postgresql','-U','postgres','-d','mrjam_identite','-f','-'],
        env=env,input=("BEGIN READ ONLY; SET LOCAL statement_timeout='5s'; SET LOCAL lock_timeout='2s';\n"+sql+'; COMMIT;').encode(),
        capture_output=True,timeout=10)
    exiger(r.returncode==0 and len(r.stdout)<=65536,'observation_sql')
    try:return json.loads(r.stdout)
    except (TypeError,ValueError):raise ObservationRefusee('observation_json') from None


def verifier_flux(api,modele):
    """Comparer la hiérarchie entière à l'import privé déjà contrôlé.

    Le mot de passe est ALTERNATIVE avec le lien magique, dans un sous-flux
    REQUIRED. Cela ne constitue pas une preuve d'authentification : celle-ci
    reste tirée des executions pwd ET otp fraîches de la session exacte.
    """
    flux={f['alias']:f for f in modele['authenticationFlows']}
    configurations={c['alias']:c['config'] for c in modele['authenticatorConfig']}
    attendues=[]
    def parcourir(alias,niveau,pile=()):
        exiger(alias in flux and alias not in pile and niveau<8,'observation_modele')
        for e in sorted(flux[alias]['authenticationExecutions'],key=lambda x:x['priority']):
            attendues.append((e,niveau))
            if e.get('authenticatorFlow'):parcourir(e['flowAlias'],niveau+1,pile+(alias,))
    exiger(modele.get('browserFlow')=='mrjam-browser','observation_modele')
    parcourir('mrjam-browser',0)
    actuelles=api('/admin/realms/mrjam/authentication/flows/mrjam-browser/executions')
    exiger(isinstance(actuelles,list) and len(actuelles)==len(attendues),'observation_hierarchie')
    resultats={};identifiants=set()
    methodes={'auth-username-password-form':('mrjam-mot-de-passe','pwd'),'auth-otp-form':('mrjam-second-facteur','otp')}
    for actuel,(attendu,niveau) in zip(actuelles,attendues):
        identifiant=actuel.get('id')
        exiger(isinstance(identifiant,str) and re.fullmatch(UUID,identifiant) and identifiant not in identifiants,'observation_identifiant')
        identifiants.add(identifiant)
        sous_flux=attendu.get('authenticatorFlow') is True
        exiger(actuel.get('requirement')==attendu['requirement'] and
            type(actuel.get('level')) is int and actuel['level']==niveau and
            type(actuel.get('priority')) is int and actuel['priority']==attendu['priority'] and
            (actuel.get('authenticationFlow') is True)==sous_flux,'observation_hierarchie')
        if sous_flux:
            exiger(actuel.get('displayName')==attendu['flowAlias'] and
                isinstance(actuel.get('flowId'),str) and re.fullmatch(UUID,actuel['flowId']),'observation_hierarchie')
        else:exiger(actuel.get('providerId')==attendu['authenticator'],'observation_provider')
        alias=attendu.get('authenticatorConfig')
        if alias:
            cfg_id=actuel.get('authenticationConfig')
            exiger(isinstance(cfg_id,str) and re.fullmatch(UUID,cfg_id),'observation_identifiant')
            cfg=api('/admin/realms/mrjam/authentication/config/'+cfg_id)
            valeurs=cfg.get('config')
            exiger(cfg.get('id')==cfg_id and cfg.get('alias')==alias and isinstance(valeurs,dict) and
                set(valeurs)==set(configurations[alias]) and all(valeurs[k] in
                    (configurations[alias][k],'**********') for k in valeurs),'observation_configuration')
        else:exiger(not actuel.get('authenticationConfig'),'observation_configuration')
        if actuel.get('providerId') in methodes:
            attendu_alias,methode=methodes[actuel['providerId']]
            exiger(alias==attendu_alias,'observation_configuration')
            resultats.setdefault(methode,[]).append(identifiant)
    exiger(set(resultats)=={'pwd','otp'} and all(len(v)==1 for v in resultats.values()),'observation_methodes')
    return resultats


def executions(api,runuser,psql,modele):
    resultats=verifier_flux(api,modele)
    sql="SELECT json_object_agg(alias,config) FROM (SELECT c.alias,json_object_agg(e.name,e.value) AS config FROM authenticator_config c JOIN authenticator_config_entry e ON e.authenticator_id=c.id WHERE c.realm_id=(SELECT id FROM realm WHERE name='mrjam') AND c.alias IN ('mrjam-mot-de-passe','mrjam-second-facteur','mrjam-lien-courriel') GROUP BY c.alias) q"
    configurations=sql_prive(runuser,psql,sql)
    exiger(configurations=={'mrjam-mot-de-passe':{'default.reference.value':'pwd','default.reference.maxAge':'300'},
        'mrjam-second-facteur':{'default.reference.value':'otp','default.reference.maxAge':'300'},
        'mrjam-lien-courriel':{'default.reference.value':'email','default.reference.maxAge':'300'}},'observation_methodes')
    return resultats


def sessions(runuser,psql,sujet):
    if not isinstance(sujet,str) or not re.fullmatch(UUID,sujet):raise ValueError('Sujet initial différent')
    sql="SELECT COALESCE(json_agg(preuve),'[]'::json) FROM (SELECT json_build_object('authMethod', data::json->'authMethod','notes',json_build_object('AUTH_TIME',data::json->'notes'->'AUTH_TIME','authenticators-completed',data::json->'notes'->'authenticators-completed')) AS preuve FROM offline_user_session WHERE user_id='"+sujet+"' AND realm_id=(SELECT id FROM realm WHERE name='mrjam') AND offline_flag='0' LIMIT 32) q"
    return sql_prive(runuser,psql,sql)
