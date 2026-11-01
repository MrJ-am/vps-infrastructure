set -eu
psql -X -h /run/postgresql -d postgres -v ON_ERROR_STOP=1 <<'SQL'
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='etp_carnet') THEN
    CREATE ROLE etp_carnet LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
  END IF;
  IF EXISTS (SELECT FROM pg_roles WHERE rolname='etp_carnet' AND (rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls)) THEN
    RAISE EXCEPTION 'Unexpected ViSe role privileges';
  END IF;
END $$;
SELECT 'CREATE DATABASE etp_carnet OWNER etp_carnet' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname='etp_carnet') \gexec
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_database d JOIN pg_roles r ON r.oid=d.datdba WHERE d.datname='etp_carnet' AND r.rolname='etp_carnet') THEN
    RAISE EXCEPTION 'Unexpected database owner';
  END IF;
END $$;
REVOKE ALL ON DATABASE etp_carnet FROM PUBLIC;
\connect etp_carnet
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE, CREATE ON SCHEMA public TO etp_carnet;
SQL
