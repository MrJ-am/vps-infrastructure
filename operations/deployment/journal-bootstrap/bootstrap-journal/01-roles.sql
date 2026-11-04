-- Source inactive : exclusivement les nouvelles identités du journal dédié.
BEGIN;
DO $$
BEGIN
 IF EXISTS(SELECT FROM pg_database WHERE datname='vision_journal')
 OR EXISTS(SELECT FROM pg_roles WHERE rolname IN (
  'vision_journal_owner','vision_journal_writer','vision_journal_archiviste',
  'vision_journal_rejeu','vision_journal_fermeture','vision_journal_import'))
 THEN RAISE EXCEPTION 'journal_bootstrap_requires_absent_database_and_roles'; END IF;
END $$;
CREATE ROLE vision_journal_owner NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;
CREATE ROLE vision_journal_writer LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS PASSWORD NULL;
CREATE ROLE vision_journal_archiviste LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS PASSWORD NULL;
CREATE ROLE vision_journal_rejeu LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS PASSWORD NULL;
CREATE ROLE vision_journal_fermeture LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS PASSWORD NULL;
-- L'import est une opération ponctuelle : connexion désactivée au bootstrap.
CREATE ROLE vision_journal_import NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS PASSWORD NULL;
COMMIT;
