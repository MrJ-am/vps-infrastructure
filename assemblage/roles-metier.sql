-- Installation explicite par l'opérateur, jamais au chargement ASDF/démarrage.
-- Rôles étroits du seul compte Unix mrjam-metier ; aucun rôle propriétaire.
\set ON_ERROR_STOP on
\connect vision
BEGIN;
DO $$ BEGIN
 IF NOT EXISTS(SELECT FROM pg_roles WHERE rolname='vision_entretien') THEN CREATE ROLE vision_entretien LOGIN; END IF;
END $$;
ALTER ROLE vision_entretien NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
REVOKE vision_migration FROM vision_entretien;
REVOKE ALL ON DATABASE vision FROM vision_entretien;
GRANT CONNECT ON DATABASE vision TO vision_entretien;
REVOKE ALL ON SCHEMA public,vision_gestion FROM vision_entretien;
GRANT USAGE ON SCHEMA vision_gestion TO vision_entretien;
REVOKE ALL ON ALL TABLES IN SCHEMA public,vision_gestion FROM vision_entretien;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA vision_gestion FROM vision_entretien;
GRANT EXECUTE ON FUNCTION vision_gestion.purger(),vision_gestion.purger_admissions() TO vision_entretien;
COMMIT;
\connect matheval
BEGIN;
DO $$ BEGIN
 IF NOT EXISTS(SELECT FROM pg_roles WHERE rolname='matheval_app') THEN CREATE ROLE matheval_app LOGIN; END IF;
END $$;
ALTER ROLE matheval_app NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
REVOKE ALL ON DATABASE matheval FROM matheval_app;
GRANT CONNECT ON DATABASE matheval TO matheval_app;
REVOKE ALL ON SCHEMA public FROM matheval_app;
GRANT USAGE ON SCHEMA public TO matheval_app;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM matheval_app;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM matheval_app;
GRANT SELECT ON corpus TO matheval_app;
GRANT SELECT,INSERT,UPDATE ON participations TO matheval_app;
GRANT SELECT,INSERT,DELETE ON answers TO matheval_app;
GRANT SELECT,INSERT ON interaction_events TO matheval_app;
GRANT SELECT,INSERT,UPDATE ON administrators TO matheval_app;
GRANT SELECT,INSERT,UPDATE,DELETE ON administrator_sessions TO matheval_app;
GRANT USAGE,SELECT ON SEQUENCE administrators_id_seq TO matheval_app;
COMMIT;
