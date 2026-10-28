\set ON_ERROR_STOP on
-- Exécuté explicitement par le mécanisme central, jamais par ASDF.
BEGIN;
DO $$ BEGIN
 IF NOT EXISTS(SELECT FROM pg_roles WHERE rolname='audition_app') THEN CREATE ROLE audition_app LOGIN; END IF;
END $$;
ALTER ROLE audition_app NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
DO $$ BEGIN EXECUTE format('GRANT CONNECT ON DATABASE %I TO audition_app', current_database()); END $$;
REVOKE ALL ON SCHEMA public,vision_gestion FROM audition_app;
GRANT USAGE ON SCHEMA audition TO audition_app;
GRANT SELECT ON audition.schema_migrations,audition.administrateurs TO audition_app;
GRANT SELECT,INSERT,DELETE ON audition.groupes TO audition_app;
GRANT SELECT,INSERT,UPDATE,DELETE ON audition.membres TO audition_app;
GRANT SELECT,INSERT,UPDATE ON audition.objets TO audition_app;
GRANT SELECT,INSERT ON audition.versions,audition.requetes,audition.audit TO audition_app;
GRANT USAGE,SELECT ON SEQUENCE audition.audit_id_seq TO audition_app;
GRANT EXECUTE ON FUNCTION audition.est_admin(),audition.role_groupe(text) TO audition_app;
COMMIT;
