-- Fixed, explicit PostgreSQL adoption operation. Not executed by a NixOS
-- activation or service start. Backup/restore and release admission precede it.
-- Run only in the existing etp_carnet database as the local PostgreSQL operator.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';
DO $adoption$
DECLARE runtime_oid oid;
BEGIN
  IF current_database() <> 'etp_carnet' OR current_user <> 'postgres' THEN
    RAISE EXCEPTION 'VISE_ADOPTION_CONTEXT_REFUSED';
  END IF;
  SELECT oid INTO STRICT runtime_oid FROM pg_roles WHERE rolname = 'etp_carnet';
  IF EXISTS (SELECT FROM pg_roles WHERE oid = runtime_oid AND
      (rolsuper OR rolcreaterole OR rolcreatedb OR rolreplication OR rolbypassrls))
     OR EXISTS (SELECT FROM pg_auth_members WHERE member = runtime_oid)
     OR EXISTS (SELECT FROM pg_database WHERE datdba = runtime_oid AND datname <> 'etp_carnet')
     OR EXISTS (SELECT FROM pg_tablespace WHERE spcowner = runtime_oid) THEN
    RAISE EXCEPTION 'VISE_ADOPTION_PRIVILEGES_REFUSED';
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'mrjam_vise_schema') THEN
    CREATE ROLE mrjam_vise_schema NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;
  END IF;
  IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'mrjam_vise_schema' AND
      (rolcanlogin OR rolsuper OR rolcreaterole OR rolcreatedb OR rolreplication OR rolbypassrls))
     OR EXISTS (SELECT FROM pg_auth_members WHERE roleid = (SELECT oid FROM pg_roles WHERE rolname = 'mrjam_vise_schema')
        OR member = (SELECT oid FROM pg_roles WHERE rolname = 'mrjam_vise_schema')) THEN
    RAISE EXCEPTION 'VISE_ADOPTION_SCHEMA_ROLE_REFUSED';
  END IF;
END
$adoption$;
REASSIGN OWNED BY etp_carnet TO mrjam_vise_schema;
ALTER DATABASE etp_carnet OWNER TO mrjam_vise_schema;
REVOKE CREATE, TEMPORARY ON DATABASE etp_carnet FROM PUBLIC, etp_carnet;
REVOKE CREATE ON SCHEMA public FROM PUBLIC, etp_carnet;
GRANT CONNECT ON DATABASE etp_carnet TO etp_carnet;
GRANT USAGE ON SCHEMA public TO etp_carnet;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO etp_carnet;
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO etp_carnet;
ALTER DEFAULT PRIVILEGES FOR ROLE mrjam_vise_schema IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO etp_carnet;
ALTER DEFAULT PRIVILEGES FOR ROLE mrjam_vise_schema IN SCHEMA public
  GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO etp_carnet;
COMMIT;
