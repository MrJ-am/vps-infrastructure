"""Garde de reprise ciblée de l’essai f9 ; jamais un effacement automatique."""
REVISION='f9dae92a39f350d5aa5b5795f74b04f6827d60ff'

def verifier_cluster(cluster):
    if not all(cluster.get(k) is True for k in ('present','dossier_prive','version17','controle_disponible','journal_disponible')):raise ValueError('Cluster non qualifié')
    if cluster.get('etat')!='shut down' or cluster.get('pid_present') is not False or cluster.get('socket_present') is not False or cluster.get('categories')!=[]:raise ValueError('Cluster actif ou différent')

def verifier(rapport):
    ok=isinstance(rapport,dict) and rapport.get('revision')==REVISION
    ok=ok and all(rapport.get(k) is True for k in ('socle_conserve','retour_termine','cluster_prive_present'))
    ok=ok and all(rapport.get(k) is False for k in ('generation_enregistree','activation','inscriptions'))
    if not ok:raise ValueError('Reprise privée non conforme')
    if rapport.get('categories')!=['commande_refusee']:raise ValueError('Cause différente')
    worker=rapport.get('worker',{})
    if worker.get('etat') not in ('inactive','failed') or (type(worker.get('code')) is not int or not 0<=worker['code']<=255):raise ValueError('Worker non arrêté')
    etapes=rapport.get('controle_worker',{})
    if etapes.get('etapes')!=['essai_generation'] or etapes.get('categories')!=[]:raise ValueError('Étape différente')
    if rapport.get('unites_echec')!=dict(bilan_present=True,connues=['nginx.service'],inconnues=0):raise ValueError('Bilan différent')
    verifier_cluster(rapport.get('cluster',{}))
    if rapport.get('import_prive')!=dict(import_verifie=True,secret_amorcage_format_verifie=True):raise ValueError('Import différent')
    return True
