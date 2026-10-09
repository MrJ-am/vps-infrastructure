"""Garde de reprise ciblée de l’essai c527 ; jamais un effacement automatique."""
REVISION='c527fcfd64dc5478da1011aafc28ce6e3d3fd199'

def verifier_cluster(cluster):
    if not all(cluster.get(k) is True for k in ('present','dossier_prive','version17','controle_disponible','journal_disponible')):raise ValueError('Cluster non qualifié')
    if cluster.get('etat')!='shut down' or cluster.get('pid_present') is not False or cluster.get('socket_present') is not False or cluster.get('categories')!=[]:raise ValueError('Cluster actif ou différent')

def verifier(rapport):
    ok=isinstance(rapport,dict) and rapport.get('revision')==REVISION
    ok=ok and all(rapport.get(k) is True for k in ('socle_conserve','retour_termine','cluster_prive_present'))
    ok=ok and all(rapport.get(k) is False for k in ('generation_enregistree','activation','inscriptions'))
    if not ok:raise ValueError('Reprise privée non conforme')
    if rapport.get('categories')!=[] or rapport.get('exception_privee')!=dict(classes=['ConstructionRefusee','HTTPError'],codes_http=[503]):raise ValueError('Cause différente')
    worker=rapport.get('worker',{})
    if worker.get('etat') not in ('inactive','failed') or (type(worker.get('code')) is not int or not 0<=worker['code']<=255):raise ValueError('Worker non arrêté')
    etapes=rapport.get('controle_worker',{})
    if etapes.get('etapes')!=['essai_generation','controles_locaux'] or etapes.get('categories')!=[]:raise ValueError('Étape différente')
    if rapport.get('unites_echec')!=dict(bilan_present=False,connues=[],inconnues=0):raise ValueError('Bilan différent')
    if rapport.get('cadres_disponibles') is not True or not all(c in rapport.get('cadres',[]) for c in (dict(script='vision-identite-amorcage-activer.py',fonction='verifier_local',ligne=321),dict(script='identite-amorcage-controle.py',fonction='verifier',ligne=34),dict(script='identite-amorcage-controle.py',fonction='api',ligne=24))):raise ValueError('Source ou contrôle différents')
    unites=rapport.get('unites_identite',{})
    if set(unites)!={'mrjam-amorcage-postgresql','mrjam-amorcage-identite','mrjam-amorcage-sauvegarde'}:raise ValueError('Unités privées différentes')
    for u in unites.values():
        if not all(u.get(k) is True for k in ('etat_disponible','journal_disponible')) or u.get('etat')!='inactive' or type(u.get('code')) is not int or u['code']!=0 or u.get('resultat')!='success':raise ValueError('Unité privée active ou différente')
    verifier_cluster(rapport.get('cluster',{}))
    if rapport.get('import_prive')!=dict(import_verifie=True,secret_amorcage_format_verifie=True):raise ValueError('Import différent')
    return True
