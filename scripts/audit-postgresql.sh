#!/bin/sh
# Lecture seule, sur le VPS. Ne lit ni mots de passe ni données applicatives.
set -eu
runuser -u postgres -- psql -X --host=/run/postgresql --dbname=postgres --set=ON_ERROR_STOP=1 <<'SQL'
SHOW server_version;
SHOW data_directory;
SHOW unix_socket_directories;
SHOW listen_addresses;
SELECT datname, pg_get_userbyid(datdba) AS owner, datacl
  FROM pg_database WHERE NOT datistemplate ORDER BY datname;
SELECT rolname, rolcanlogin, rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls
  FROM pg_roles WHERE rolname !~ '^pg_' ORDER BY rolname;
SELECT pg_get_userbyid(member) AS member, pg_get_userbyid(roleid) AS granted_role
  FROM pg_auth_members ORDER BY 1, 2;
SELECT line_number, type, database, user_name, address, auth_method, error
  FROM pg_hba_file_rules ORDER BY line_number;
SQL
runuser -u postgres -- psql -X --host=/run/postgresql --dbname=matheval --set=ON_ERROR_STOP=1 <<'SQL'
SELECT nspname, pg_get_userbyid(nspowner) AS owner, nspacl
  FROM pg_namespace WHERE nspname = 'public';
SQL
