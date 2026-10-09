"""Observer le seul compte durable, sans création, courriel ou modification API."""
import re
import time

ISSUER = 'https://log.mrj.am/realms/mrjam'
UUID = r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}'


def exiger(condition):
    if not condition: raise ValueError('Observation du compte initial refusée')


def verifier_compte(api, contact, etat, executions):
    compte = etat.get('compte.json')
    exiger(isinstance(compte, dict) and set(compte) == {'issuer', 'sujet', 'courriel', 'nom_connexion'} and
        compte['issuer'] == ISSUER and compte['courriel'] == contact['courriel'] and
        compte['nom_connexion'] == contact['nom_connexion'] and
        isinstance(compte['sujet'], str) and re.fullmatch(UUID, compte['sujet']))
    exiger(all(etat.get(nom) == {} for nom in ('creation-demandee', 'courriel-demande', 'courriel-accepte')) and
        etat.get('executions.json') == executions)
    base = '/admin/realms/mrjam'
    comptes = api(base + '/users?max=2')
    exiger(isinstance(comptes, list) and len(comptes) == 1 and comptes[0].get('id') == compte['sujet'])
    chemin = base + '/users/' + compte['sujet']
    actuel = api(chemin)
    exiger(actuel.get('id') == compte['sujet'] and actuel.get('email') == contact['courriel'] and
        actuel.get('username', '').lower() == contact['nom_connexion'].lower() and
        actuel.get('enabled') is True and actuel.get('emailVerified') is True and
        actuel.get('requiredActions', []) == [])
    credentials = api(chemin + '/credentials')
    exiger(isinstance(credentials, list) and len(credentials) == 2 and
        {c.get('type') for c in credentials} == {'password', 'otp'})
    clients = api(base + '/clients?clientId=realm-management')
    exiger(isinstance(clients, list) and len(clients) == 1 and
        isinstance(clients[0].get('id'), str) and re.fullmatch(UUID, clients[0]['id']))
    exiger(api(chemin + '/role-mappings/clients/' + clients[0]['id'] + '/composite') == [])
    return compte['sujet']


def attendre_connexion(lire_sessions, verifier_notes, executions, *, maximum=600,
                      horloge=time.time, monotone=time.monotonic, pause=time.sleep):
    """Ne réessayer que la projection SQL READ ONLY ; aucun autre effet rejoué."""
    exiger(type(maximum) is int and 0 <= maximum <= 600)
    limite = monotone() + maximum
    while True:
        sessions = lire_sessions()
        exiger(isinstance(sessions, list) and len(sessions) <= 32)
        maintenant = int(horloge())
        if any(verifier_notes(v, executions, maintenant) for v in sessions): return maintenant
        restant = limite - monotone()
        if restant <= 0: return None
        pause(min(5, restant))
