# Real PostgreSQL, invented rows only, no production source or connection.
{ pkgs, matevalSource }:
pkgs.runCommand "mrjam-matheval-role-adoption-synthetic" {
  nativeBuildInputs = [ pkgs.postgresql_17 pkgs.coreutils pkgs.gnused ];
} ''
  set -eu
  mkdir socket
  initdb -D data -U postgres --no-locale --auth-local=trust >/dev/null
  pg_ctl -D data -o "-k $PWD/socket -c listen_addresses=" -l postgres.log start >/dev/null
  trap 'pg_ctl -D data -m fast stop >/dev/null || true' EXIT
  export PGHOST="$PWD/socket" PGUSER=postgres
  if psql -X -w -v ON_ERROR_STOP=1 -d postgres -f ${./adopt-matheval.sql} > wrong-target.log 2>&1; then
    exit 1
  fi
  test "$(psql -X -At -d postgres -c "SELECT count(*) FROM pg_roles WHERE rolname IN ('mrjam_matheval_owner','matheval_admin')")" = 0
  psql -X -w -v ON_ERROR_STOP=1 -d postgres <<'SQL' >/dev/null
  CREATE ROLE matheval_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
  CREATE DATABASE matheval OWNER matheval_app;
  SQL
  psql -X -w -v ON_ERROR_STOP=1 -d matheval -f ${matevalSource}/migrations/001-collecte.sql >/dev/null
  psql -X -w -v ON_ERROR_STOP=1 -d matheval -f ${matevalSource}/migrations/002-sessions-administrateur.sql >/dev/null
  psql -X -w -v ON_ERROR_STOP=1 -d matheval <<'SQL' >/dev/null
  INSERT INTO corpus(version,digest,bank,codebook) VALUES('synthetic','invented','{}','{}');
  INSERT INTO administrators(username,password_hash) VALUES('synthetic-admin','synthetic-hash');
  INSERT INTO administrator_sessions(token_hash,administrator_id,expires_at,last_seen)
    VALUES('synthetic-session',1,'2030-01-01','2026-10-01');
  GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public TO matheval_app;
  GRANT UPDATE(username),SELECT(password_hash) ON administrators TO matheval_app;
  SQL
  pg_dump --data-only --no-owner --no-privileges -d matheval | sed '/^\\restrict /d; /^\\unrestrict /d' > before.sql
  psql -X -w -v ON_ERROR_STOP=1 -d matheval -f ${./adopt-matheval.sql} > adopt.log 2>&1
  pg_dump --data-only --no-owner --no-privileges -d matheval | sed '/^\\restrict /d; /^\\unrestrict /d' > after.sql
  cmp before.sql after.sql
  psql -X -w -v ON_ERROR_STOP=1 -d matheval <<'SQL' >/dev/null
  DO $check$
  BEGIN
    IF NOT has_table_privilege('matheval_app','public.corpus','SELECT')
       OR has_table_privilege('matheval_app','public.corpus','INSERT,UPDATE,DELETE')
       OR has_any_column_privilege('matheval_app','public.administrators','SELECT,INSERT,UPDATE,REFERENCES')
       OR has_table_privilege('matheval_app','public.administrator_sessions','SELECT,INSERT,UPDATE,DELETE')
       OR has_schema_privilege('matheval_app','public','CREATE')
       OR has_database_privilege('matheval_app','matheval','CREATE,TEMP')
       OR NOT has_table_privilege('matheval_admin','public.administrator_sessions','SELECT,INSERT,UPDATE,DELETE')
       OR has_column_privilege('matheval_admin','public.administrators','password_hash','UPDATE')
       OR has_schema_privilege('matheval_admin','public','CREATE')
       OR EXISTS(SELECT FROM pg_auth_members WHERE member IN (SELECT oid FROM pg_roles WHERE rolname IN ('matheval_app','matheval_admin')))
    THEN RAISE EXCEPTION 'CAPABILITY_CONTRACT_FAILED'; END IF;
  END $check$;
  SET ROLE matheval_app;
  SELECT version FROM corpus;
  RESET ROLE;
  SET ROLE matheval_admin;
  UPDATE administrator_sessions SET last_seen='2026-10-02' WHERE token_hash='synthetic-session';
  RESET ROLE;
  SQL
  for command in "SET ROLE matheval_app; SELECT * FROM administrators" \
                 "SET ROLE matheval_app; DELETE FROM corpus" \
                 "SET ROLE matheval_admin; UPDATE administrators SET password_hash='changed'" \
                 "SET ROLE matheval_admin; CREATE TABLE public.forbidden(x int)"; do
    if psql -X -w -v ON_ERROR_STOP=1 -d matheval -c "$command" > denied.log 2>&1; then exit 1; fi
  done
  if psql -X -w -v ON_ERROR_STOP=1 -d matheval -f ${./adopt-matheval.sql} > repeated.log 2>&1; then exit 1; fi
  test "$(psql -X -At -d matheval -c "SELECT count(*) FROM administrators WHERE password_hash='synthetic-hash'")" = 1
  pg_ctl -D data -m fast stop >/dev/null
  trap - EXIT
  mkdir "$out"
  printf '%s\n' '{"schema_version":1,"groups":6,"passed":true,"synthetic_only":true,"production_access":false}' > "$out/result.json"
''
