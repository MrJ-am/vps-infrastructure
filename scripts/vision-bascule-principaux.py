"""Association préparatoire explicite ; aucune correspondance par adresse email."""
from datetime import datetime
import re

ISSUER = 'https://log.mrj.am/realms/mrjam'
OBSERVATION = '0fbce8dbad7534b007d5f127d55f4071962f9ccb'
UUID = r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}'


def exiger(condition):
    if not condition: raise ValueError('Preuve de rattachement préparatoire refusée')


def verifier_preuve(public, compte, preuves):
    exiger(public.get('infrastructure') == OBSERVATION and public.get('execution') == 38002451652 and
        public.get('job') == 114063522619 and all(public.get(k) is True for k in
        ('compte_initial_verifie', 'courriel_verifie', 'mot_de_passe_configure', 'second_facteur_configure',
         'pwd_otp_frais_au_controle', 'recu_prive_ecrit', 'services_conserves')) and
        all(public.get(k) is False for k in ('privilege_administrateur_identite', 'mode_vision_oidc', 'inscriptions')))
    exiger(isinstance(compte, dict) and compte.get('issuer') == ISSUER and
        isinstance(compte.get('sujet'), str) and re.fullmatch(UUID, compte['sujet']))
    debut = int(datetime.fromisoformat(public['debut'].replace('Z', '+00:00')).timestamp())
    fin = int(datetime.fromisoformat(public['fin'].replace('Z', '+00:00')).timestamp())
    exiger(0 < fin-debut <= 1200 and isinstance(preuves, dict) and len(preuves) == 1)
    nom, preuve = next(iter(preuves.items()))
    exiger(isinstance(preuve, dict) and set(preuve) == {'version', 'issuer', 'sujet', 'pwd_otp_frais', 'date'} and
        type(preuve['version']) is int and preuve['version'] == 1 and preuve['issuer'] == ISSUER and
        preuve['sujet'] == compte['sujet'] and preuve['pwd_otp_frais'] is True and
        type(preuve['date']) is int and debut <= preuve['date'] <= fin and
        nom == 'connexion-'+str(preuve['date'])+'.json')
    # Preuve durable de possession à l'amorçage ; aucune fraîcheur actuelle annoncée.
    return dict(issuer=ISSUER, sujet=compte['sujet'], possession_verifiee_a=preuve['date'])


def association_sql(identite, historique, litteral):
    exiger(isinstance(identite, dict) and identite.get('issuer') == ISSUER and
        isinstance(identite.get('sujet'), str) and re.fullmatch(UUID, identite['sujet']))
    exiger(isinstance(historique, dict) and historique.get('proprietaires') == 1 and
        historique.get('authentification_unique') is True and
        isinstance(historique.get('utilisateur_historique'), str) and
        re.fullmatch(r'[A-Za-z0-9_.-]{1,64}', historique['utilisateur_historique']))
    u, emetteur, sujet = map(litteral, (historique['utilisateur_historique'], ISSUER, identite['sujet']))
    return """BEGIN;
SET LOCAL lock_timeout='5s'; SET LOCAL statement_timeout='15s';
LOCK TABLE vision_gestion.comptes,vision_gestion.identites IN ACCESS EXCLUSIVE MODE;
DO $$ BEGIN
 IF (SELECT count(*) FROM vision_gestion.comptes)<>1
  OR NOT EXISTS(SELECT FROM vision_gestion.comptes WHERE utilisateur="""+u+""" AND actif)
  OR EXISTS(SELECT FROM vision_gestion.identites)
  OR EXISTS(SELECT FROM vision_gestion.configuration WHERE inscriptions_ouvertes)
  OR (SELECT count(*) FROM vision_schema_migrations WHERE version BETWEEN 19 AND 25)<>7 THEN
  RAISE EXCEPTION 'association_preparatoire_ambigue';
 END IF;
END $$;
INSERT INTO vision_gestion.identites(emetteur,sujet,utilisateur) VALUES("""+emetteur+','+sujet+','+u+""");
UPDATE vision_gestion.comptes SET administrateur=true WHERE utilisateur="""+u+""";
COMMIT;"""


def verifier_isole(socket, resultat):
    exiger(isinstance(socket, str) and re.fullmatch(r'/var/lib/postgresql/vision-bascule-[a-f0-9]{12}', socket))
    exiger(resultat == dict(tcp='', socket=socket, data=socket+'/data', encodage='UTF8', majeure=17))
