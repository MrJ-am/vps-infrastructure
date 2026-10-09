"""Créer seulement le compte initial ; aucun mot de passe choisi par l'exploitation."""
import json
import re
import urllib.parse

ISSUER = 'https://log.mrj.am/realms/mrjam'
ACTIONS = ['UPDATE_PASSWORD', 'CONFIGURE_TOTP']
UUID = r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}'


def exiger(condition):
    if not condition: raise ValueError('Enrôlement privé interrompu ; diagnostic local requis')


def verifier_enveloppe(valeur):
    exiger(isinstance(valeur, dict) and set(valeur) == {'version','objet','issuer','courriel','nom_connexion'})
    exiger(type(valeur['version']) is int and valeur['version'] == 1 and
        valeur['objet'] == 'mrjam-enrolement-proprietaire' and valeur['issuer'] == ISSUER)
    exiger(isinstance(valeur['courriel'], str) and
        re.fullmatch(r'[A-Za-z0-9._+-]{1,64}@[A-Za-z0-9.-]{1,190}', valeur['courriel']) and
        isinstance(valeur['nom_connexion'], str) and re.fullmatch(r'[A-Za-z0-9._-]{2,64}', valeur['nom_connexion']))
    return {**valeur, "courriel": valeur["courriel"].lower()}


def preparer_compte(api, identite, lire, ecrire, *, realm='mrjam', redirect=None):
    """Les marqueurs sont fsync avant effets ; une réponse perdue ne provoque aucun rejeu."""
    identite = verifier_enveloppe(identite)
    base = '/admin/realms/' + realm
    comptes = api(base+'/users?max=2')
    compte = lire('compte.json')
    if compte is None:
        exiger(comptes == [] and lire('creation-demandee') is None)
        ecrire('creation-demandee', {})
        _code, _corps, entetes = api(base+'/users', dict(username=identite['nom_connexion'],
            email=identite['courriel'], enabled=True, emailVerified=False, requiredActions=ACTIONS), 'POST')
        chemin = urllib.parse.urlsplit(entetes.get('Location','')).path
        exiger(_code==201 and chemin.startswith(base+'/users/') and re.fullmatch(UUID, chemin[len(base+'/users/'):]))
        sujet = chemin[len(base+'/users/'):]
        compte = dict(issuer=ISSUER, sujet=sujet, courriel=identite['courriel'], nom_connexion=identite['nom_connexion'])
        ecrire('compte.json', compte)
        comptes = api(base+'/users?max=2')
    exiger(isinstance(compte, dict) and set(compte)=={'issuer','sujet','courriel','nom_connexion'} and
        compte['issuer']==ISSUER and compte['courriel']==identite['courriel'] and
        compte['nom_connexion']==identite['nom_connexion'] and re.fullmatch(UUID,compte['sujet']))
    exiger(isinstance(comptes,list) and len(comptes)==1 and comptes[0].get('id')==compte['sujet'])
    chemin = base+'/users/'+compte['sujet']
    actuel = api(chemin)
    exiger(actuel.get('id')==compte['sujet'] and actuel.get('email')==identite['courriel'] and
        actuel.get('username','').lower()==identite['nom_connexion'].lower() and actuel.get('enabled') is True)
    clients = api(base+'/clients?clientId=realm-management')
    exiger(isinstance(clients,list) and len(clients)==1 and
        re.fullmatch(UUID,clients[0].get('id','')))
    exiger(api(chemin+'/role-mappings/clients/'+clients[0]['id']+'/composite')==[])
    if lire('courriel-accepte') is None:
        exiger(lire('courriel-demande') is None and actuel.get('emailVerified') is False and
            set(actuel.get('requiredActions',[]))==set(ACTIONS) and api(chemin+'/credentials')==[])
        params = urllib.parse.urlencode(dict(lifespan=1800,client_id='account-console',
            redirect_uri=redirect or ISSUER+'/account/'))
        ecrire('courriel-demande', {})
        code,_corps,_entetes=api(chemin+'/execute-actions-email?'+params, ACTIONS, 'PUT')
        exiger(code==204)
        ecrire('courriel-accepte', {})
    return dict(compte_initial_prepare=True, courriel_accepte_par_relais=True,
        participation_proprietaire_requise=True, mot_de_passe_fourni_par_exploitation=False,
        privilege_administrateur_identite=False, mode_vision_oidc=False, inscriptions=False)
