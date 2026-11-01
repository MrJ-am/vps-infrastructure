-- Fixed, explicit PostgreSQL adoption operation. Not executed by a NixOS
-- activation or service start. Backup/restore and release admission precede it.
-- Run only in the existing forgejo database as the local PostgreSQL operator.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';
DO $adoption$
DECLARE runtime_oid oid;
BEGIN
  IF current_database() <> 'forgejo' OR current_user <> 'postgres' THEN
    RAISE EXCEPTION 'FORGEJO_ADOPTION_CONTEXT_REFUSED';
  END IF;
  SELECT oid INTO STRICT runtime_oid FROM pg_roles WHERE rolname = 'forgejo';
  IF EXISTS (SELECT FROM pg_roles WHERE oid = runtime_oid AND
      (rolsuper OR rolcreaterole OR rolcreatedb OR rolreplication OR rolbypassrls))
     OR EXISTS (SELECT FROM pg_auth_members WHERE member = runtime_oid)
     OR EXISTS (SELECT FROM pg_database WHERE datdba = runtime_oid AND datname <> 'forgejo')
     OR EXISTS (SELECT FROM pg_tablespace WHERE spcowner = runtime_oid) THEN
    RAISE EXCEPTION 'FORGEJO_ADOPTION_PRIVILEGES_REFUSED';
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'mrjam_forgejo_schema') THEN
    CREATE ROLE mrjam_forgejo_schema NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;
  END IF;
  IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'mrjam_forgejo_schema' AND
      (rolcanlogin OR rolsuper OR rolcreaterole OR rolcreatedb OR rolreplication OR rolbypassrls))
     OR EXISTS (SELECT FROM pg_auth_members WHERE roleid = (SELECT oid FROM pg_roles WHERE rolname = 'mrjam_forgejo_schema')
        OR member = (SELECT oid FROM pg_roles WHERE rolname = 'mrjam_forgejo_schema')) THEN
    RAISE EXCEPTION 'FORGEJO_ADOPTION_SCHEMA_ROLE_REFUSED';
  END IF;
END
$adoption$;
REASSIGN OWNED BY forgejo TO mrjam_forgejo_schema;
ALTER DATABASE forgejo OWNER TO mrjam_forgejo_schema;
REVOKE CREATE, TEMPORARY ON DATABASE forgejo FROM PUBLIC, forgejo;
REVOKE CREATE ON SCHEMA public FROM PUBLIC, forgejo;
GRANT CONNECT ON DATABASE forgejo TO forgejo;
GRANT USAGE ON SCHEMA public TO forgejo;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO forgejo;
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO forgejo;
ALTER DEFAULT PRIVILEGES FOR ROLE mrjam_forgejo_schema IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO forgejo;
ALTER DEFAULT PRIVILEGES FOR ROLE mrjam_forgejo_schema IN SCHEMA public
  GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO forgejo;
COMMIT;
