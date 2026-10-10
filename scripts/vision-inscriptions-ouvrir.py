"""Ouvrir uniquement l'admission par invitation du Vision déjà enregistré.

Aucune reconstruction, migration, identité créée, invitation consommée,
lecture de contenu pédagogique ou lecture de secret SMTP.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import stat
import subprocess

ROOT = Path(__file__).resolve().parents[1]
ACTIVATION = '008671ee6eedf8bcb983b7a0435732f43f630441'
VISION = 'a9c51acac81510d7dc896f5daf4e6fb28a36b979'
SERVICES = ('sshd', 'nginx', 'postgresql', 'vision', 'matheval', 'mrj-auth',
            'keycloak', 'vision-gestion', 'vision-cycle', 'mrjam-admission',
            'mrjam-fermeture', 'mrjam-courriel.timer', 'mrjam-sauvegarde.timer')


def exiger(condition):
    if not condition:
        raise ValueError('Ouverture réservée refusée')


def dossier(path):
    info = path.lstat()
    exiger(stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o077)


def lire(path):
    dossier(path.parent)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        s = os.fstat(fd)
        exiger(stat.S_ISREG(s.st_mode) and s.st_uid == 0 and s.st_nlink == 1
               and stat.S_IMODE(s.st_mode) == 0o600 and s.st_size <= 1048576)
        with os.fdopen(fd) as f:
            fd = None
            return json.load(f)
    finally:
        if fd is not None:
            os.close(fd)


def paquet(path):
    exiger(isinstance(path, str) and re.fullmatch(r'/nix/store/[a-z0-9]{32}-[A-Za-z0-9._+-]+', path))
    return Path(path)


def ouverture_sql():
    # La réservation utilise un lien réel, dans une sous-transaction annulée.
    # Aucun secret de lien ne sort de PostgreSQL ; aucun mail n'est envoyé.
    return """BEGIN;
SET LOCAL lock_timeout='5s'; SET LOCAL statement_timeout='20s';
LOCK TABLE vision_gestion.configuration,vision_gestion.invitations,vision_gestion.admissions IN SHARE ROW EXCLUSIVE MODE;
DO $ouverture$
DECLARE i vision_gestion.invitations; n text; demande uuid; empreinte text; admissions bigint;
BEGIN
 IF NOT EXISTS(SELECT FROM vision_gestion.configuration WHERE singleton AND NOT inscriptions_ouvertes
  AND responsable IN ('','Jean-Christophe Jameux') AND lower(contact) IN ('','rgpd@mrj.am')
  AND pays_hebergement IN ('','Allemagne') AND notice_version IN ('','vision-20261010') AND sauvegardes_jours=30)
  THEN RAISE EXCEPTION 'notice_ou_etat_incompatible'; END IF;
 n:='vision-20261010';
 SELECT * INTO i FROM vision_gestion.invitations x WHERE revoque_a IS NULL AND expire_a>now()
  AND utilise+(SELECT count(*) FROM vision_gestion.admissions a WHERE a.invitation_id=x.id
   AND consommee_a IS NULL AND annulee_a IS NULL AND expire_a>now())<maximum ORDER BY cree_a DESC LIMIT 1;
 IF NOT FOUND THEN RAISE EXCEPTION 'aucune_invitation_disponible'; END IF;
 SELECT md5(coalesce(string_agg(to_jsonb(x)::text,'' ORDER BY id),'')) INTO empreinte FROM vision_gestion.invitations x;
 SELECT count(*) INTO admissions FROM vision_gestion.admissions;
 UPDATE vision_gestion.configuration SET inscriptions_ouvertes=true,
  responsable='Jean-Christophe Jameux',contact='RGPD@MrJ.am',pays_hebergement='Allemagne',notice_version=n WHERE singleton;
 BEGIN
  demande:=gen_random_uuid();
  PERFORM vision_gestion.reserver_admission(demande,i.condensat,n);
  IF NOT EXISTS(SELECT FROM vision_gestion.admissions WHERE id=demande AND invitation_id=i.id)
   THEN RAISE EXCEPTION 'qualification_reservation_refusee'; END IF;
  RAISE SQLSTATE 'V0001';
 EXCEPTION WHEN SQLSTATE 'V0001' THEN NULL;
 END;
 IF empreinte IS DISTINCT FROM (SELECT md5(coalesce(string_agg(to_jsonb(x)::text,'' ORDER BY id),'')) FROM vision_gestion.invitations x)
  OR admissions<>(SELECT count(*) FROM vision_gestion.admissions)
  THEN RAISE EXCEPTION 'qualification_non_annulee'; END IF;
END $ouverture$;
COMMIT;
SELECT inscriptions_ouvertes FROM vision_gestion.configuration WHERE singleton;
"""


class Ouverture:
    def __init__(self, revision):
        exiger(os.geteuid() == 0 and re.fullmatch('[a-f0-9]{40}', revision))
        os.umask(0o077)
        self.revision = revision
        self.d = Path('/root/vision-inscriptions') / revision
        exiger(ROOT == self.d / 'source')
        for p in (self.d.parent, self.d, ROOT): dossier(p)
        self.activation = Path('/root/vision-essais') / ACTIVATION
        dossier(self.activation.parent)
        self.plan = lire(self.activation / 'plan.json')
        self.systeme = paquet(self.plan['nouveau'])
        q = json.loads((ROOT / 'operations/vision-identite-amorcage-qualification.json').read_text())
        resume = lire(Path('/root/vision-identite-amorcage-operations') / q['infrastructure'] / 'evaluation-privee.json')
        self.psql = paquet(resume['postgres_paquet']) / 'bin/psql'
        self.runuser = paquet(resume['runuser_paquet']) / 'bin/runuser'
        self.systemctl = self.systeme / 'sw/bin/systemctl'

    def commande(self, *args, entree=None):
        r = subprocess.run([str(a) for a in args], input=entree, capture_output=True, timeout=60)
        exiger(r.returncode == 0 and len(r.stdout) <= 1048576)
        return r.stdout.decode().strip()

    def sql(self, texte, base='vision'):
        return self.commande(self.runuser, '-u', 'postgres', '--', self.psql,
            '-XAtq', '-v', 'ON_ERROR_STOP=1', '-h', '/run/postgresql', '-d', base,
            '-f', '-', entree=texte.encode())

    def ecrire(self, nom, valeur):
        fd = os.open(self.d / nom, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'w') as f:
            json.dump(valeur, f); f.flush(); os.fsync(f.fileno())
        d = os.open(self.d, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try: os.fsync(d)
        finally: os.close(d)

    def verifier(self):
        r = lire(self.activation / 'activation.json')
        exiger(r['infrastructure'] == ACTIVATION and r['vision'] == VISION and all(r.get(k) is True for k in
            ('activation', 'configuration_persistante', 'donnees_historiques_conservees',
             'identite_courante_transferee', 'administrateur_sans_contenu', 'sauvegarde_commune_executee')))
        # Aucun retour ancien ne doit être actif après admission d'un tiers.
        exiger((self.activation / 'enregistre').read_bytes() == b'1\n')
        exiger(not (self.activation / 'retour-commence').exists())
        exiger(Path('/run/current-system').resolve() == self.systeme == Path('/nix/var/nix/profiles/system').resolve())
        exiger(Path('/etc/nixos/configuration.nix').resolve() == self.activation / 'entree.nix')
        exiger(Path('/srv/vision/current').resolve() == Path(self.plan['backend']))
        self.commande(self.systemctl, 'is-active', *SERVICES)
        exiger(self.commande(self.systemctl, 'show', 'mrjam-courriel.service', '--property=Result', '--value') == 'success')
        exiger(self.sql("SELECT current_setting('listen_addresses')='' AND current_setting('unix_socket_directories')='/run/postgresql' AND current_setting('server_version_num')::int/10000=17;", 'postgres') == 't')
        exiger(self.sql("SELECT count(*)=25 AND max(version)=25 FROM vision_schema_migrations;") == 't')
        exiger(self.sql("SELECT NOT EXISTS(SELECT FROM pg_roles WHERE rolname IN ('vision','vision_administration','vision_identite','vision_cycle','vision_admission','vision_fermeture','keycloak') AND (rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls));") == 't')
        exiger(self.sql("SELECT NOT EXISTS(SELECT FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relname LIKE 'vision_%' AND c.relkind IN ('r','p','v','m') AND has_table_privilege('vision_administration',c.oid,'SELECT,INSERT,UPDATE,DELETE'));") == 't')
        exiger(self.sql("SELECT EXISTS(SELECT FROM vision_gestion.comptes c JOIN vision_gestion.identites i USING(utilisateur) WHERE c.actif AND c.administrateur AND i.emetteur='https://log.mrj.am/realms/mrjam');") == 't')

    def preparer(self):
        self.verifier()
        exiger(self.sql('SELECT NOT inscriptions_ouvertes FROM vision_gestion.configuration WHERE singleton;') == 't')
        self.ecrire('preparation.json', dict(version=1, infrastructure=self.revision, activation=ACTIVATION,
            generation_conservee=True, contenu_non_lu=True, smtp_non_lu=True, inscriptions=False))
        print(json.dumps(dict(ouverture_preparee=True, inscriptions=False)), flush=True)

    def ouvrir(self):
        exiger(lire(self.d / 'preparation.json')['infrastructure'] == self.revision)
        exiger(not (self.d / 'ouverture.json').exists())
        self.verifier()
        exiger(self.sql(ouverture_sql()) == 't')
        self.ecrire('ouverture.json', dict(infrastructure=self.revision, inscriptions=True,
            reservation_reelle_sans_consommation=True))
        print(json.dumps(dict(inscriptions=True, invitation_reelle_reservable=True,
            invitation_non_consommee=True, compte_cree=False, courriel_envoye=False)), flush=True)

    def finaliser(self):
        exiger(lire(self.d / 'ouverture.json')['infrastructure'] == self.revision)
        self.verifier()
        exiger(self.sql('SELECT inscriptions_ouvertes FROM vision_gestion.configuration WHERE singleton;') == 't')
        rapport = dict(version=1, infrastructure=self.revision, activation=ACTIVATION, vision=VISION,
            inscriptions=True, invitations_obligatoires=True, generation_conservee=True,
            notice_renseignee=True, notice_version='vision-20261010',
            association_et_administrateur_verifies=True, administrateur_sans_contenu=True,
            invitation_reelle_reservable=True, invitation_non_consommee=True,
            controles_mineurs_et_pays_conserves=True, smtp_non_lu=True, courriel_envoye=False,
            compte_cree=False, donnees_pedagogiques_lues=False)
        self.ecrire('inscriptions.json', rapport)
        print(json.dumps(rapport), flush=True)

    def fermer(self):
        # Retour uniquement du drapeau ; aucun compte ou contenu ne disparaît.
        exiger(lire(self.d / 'preparation.json')['infrastructure'] == self.revision)
        exiger(not (self.d / 'inscriptions.json').exists())
        exiger(self.sql("BEGIN; SET LOCAL lock_timeout='5s'; UPDATE vision_gestion.configuration SET inscriptions_ouvertes=false WHERE singleton; COMMIT; SELECT NOT inscriptions_ouvertes FROM vision_gestion.configuration WHERE singleton;") == 't')
        print(json.dumps(dict(inscriptions=False, fermeture_apres_refus=True, donnees_conservees=True)), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('revision'); p.add_argument('action', choices=('preparer', 'ouvrir', 'finaliser', 'fermer'))
    a = p.parse_args()
    try:
        o = Ouverture(a.revision)
        fd = os.open('/srv/vision/deploy.lock', os.O_RDWR | os.O_NOFOLLOW)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            getattr(o, a.action)()
        finally: os.close(fd)
    except Exception:
        print(json.dumps(dict(ouverture_refusee=True, phase=a.action)), flush=True)
        raise SystemExit('Ouverture refusée ; aucune donnée ou réponse privée affichée.')
