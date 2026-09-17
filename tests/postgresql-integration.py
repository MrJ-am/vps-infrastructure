#!/usr/bin/env python3
"""Vérifier les accès et les dumps dans un PostgreSQL 17 jetable, sans réseau."""
import json
import subprocess
import sys
import time


def run(*args, data=None, check=True):
    result = subprocess.run(args, input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if check and result.returncode:
        raise RuntimeError(f"{args[0]} a échoué : {result.stderr.decode(errors='replace')}")
    return result


def main(fixture_path):
    layout = json.load(open(fixture_path))
    container = run("docker", "run", "--detach", "--network=none",
                    "--env", "POSTGRES_HOST_AUTH_METHOD=trust", "postgres:17",
                    "-c", "listen_addresses=", "-c", "unix_socket_directories=/var/run/postgresql").stdout.decode().strip()

    def sql(query, database="postgres", user="postgres", role=None, check=True):
        return run("docker", "exec", "--interactive", "--user", user, container,
                   "psql", "-X", "--set=ON_ERROR_STOP=1", "--tuples-only", "--no-align",
                   "--host=/var/run/postgresql", "--username=" + (role or user),
                   "--dbname=" + database, data=query.encode(), check=check)

    def value(query, **kwargs):
        return sql(query, **kwargs).stdout.decode().strip()

    def denied(database, user, role=None, reason="rejects connection"):
        result = sql("SELECT 1;", database, user, role, check=False)
        assert result.returncode != 0, (database, user, role)
        assert reason in result.stderr.decode(), result.stderr.decode()

    try:
        for _ in range(120):
            ready = run("docker", "exec", "--user", "postgres", container,
                        "pg_isready", "--host=/var/run/postgresql", check=False)
            if ready.returncode == 0:
                # L'entrypoint démarre d'abord un serveur provisoire : attendre
                # que le processus principal soit réellement postgres.
                process = run("docker", "exec", container, "cat", "/proc/1/comm").stdout.strip()
                if process == b"postgres":
                    break
            time.sleep(0.5)
        else:
            raise RuntimeError("PostgreSQL de test ne démarre pas.")

        for name in layout["databases"]:
            run("docker", "exec", container, "useradd", "--no-create-home", name)

        # Base existante avant le transfert : ses données doivent survivre.
        sql('CREATE ROLE matheval LOGIN; CREATE DATABASE matheval OWNER matheval;')
        sql("CREATE TABLE original_data (value text); INSERT INTO original_data VALUES ('preserved');",
            "matheval", "matheval")

        # Même provisionnement que ensureDatabases / ensureUsers de NixOS.
        for user in layout["users"]:
            name = user["name"]
            if value(f"SELECT count(*) FROM pg_database WHERE datname='{name}';") == "0":
                sql(f'CREATE DATABASE "{name}";')
            if value(f"SELECT count(*) FROM pg_roles WHERE rolname='{name}';") == "0":
                sql(f'CREATE ROLE "{name}" LOGIN;')
            clauses = " ".join(("" if enabled else "NO") + clause.upper()
                               for clause, enabled in user["ensureClauses"].items())
            sql(f'ALTER ROLE "{name}" {clauses}; ALTER DATABASE "{name}" OWNER TO "{name}";')

        sql(layout["permissionsSQL"])
        run("docker", "exec", "--interactive", container, "sh", "-c",
            'cat > "$PGDATA/pg_hba.conf"', data=layout["authentication"].encode())
        sql("SELECT pg_reload_conf();")
        for _ in range(40):
            result = sql("SELECT 1;", "vision", "matheval", check=False)
            if result.returncode:
                break
            time.sleep(0.1)
        assert value("SELECT count(*) FROM pg_hba_file_rules WHERE error IS NOT NULL;") == "0"
        assert value("SHOW listen_addresses;") == ""

        for name, other in (("matheval", "vision"), ("vision", "matheval")):
            assert value("SELECT current_user;", database=name, user=name) == name
            sql(f"CREATE TABLE owner_probe (value text); INSERT INTO owner_probe VALUES ('{name}');", name, name)
            denied(other, name)
            denied("postgres", name)
            denied(other, name, other, "Peer authentication failed")
            assert value(f"SELECT has_database_privilege('{name}', '{other}', 'CONNECT');") == "f"
            assert value(f"SELECT has_schema_privilege('{other}', 'public', 'CREATE');", database=name) == "f"
            assert value(f"SELECT rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls "
                         f"FROM pg_roles WHERE rolname='{name}';") == "f"

        denied("postgres", "root", "postgres", "Peer authentication failed")
        sql(layout["permissionsSQL"])  # réapplication sans réinitialiser les bases
        assert value("SELECT value FROM original_data;", database="matheval", user="matheval") == "preserved"

        # Dump et restauration séparés, avec les mêmes outils de version 17.
        for name in layout["databases"]:
            dump = run("docker", "exec", "--user", "postgres", container,
                       "pg_dump", "--host=/var/run/postgresql", "--format=custom", name).stdout
            sql(f'CREATE DATABASE "restored_{name}";')
            run("docker", "exec", "--interactive", "--user", "postgres", container,
                "pg_restore", "--exit-on-error", "--no-owner", "--host=/var/run/postgresql",
                "--dbname=restored_" + name, data=dump)
            assert value("SELECT value FROM owner_probe;", database="restored_" + name) == name
        print("PostgreSQL 17 : accès séparés, droits limités, données conservées, ACL réapplicables et restaurations vérifiés.")
    finally:
        run("docker", "rm", "--force", "--volumes", container)


if __name__ == "__main__":
    main(sys.argv[1])
