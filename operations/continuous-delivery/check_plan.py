"""Exercise a release's migrations only on disposable local PostgreSQL."""
import json
import os
from pathlib import Path
import subprocess
import sys

import migrations


def main(path, psql):
    plan = migrations.load(path)
    root = Path(path).parent
    databases = {}
    for step in plan["steps"]:
        if step["driver"] == "program":
            subprocess.run([step["package"] + "/bin/check"], check=True, timeout=1200)
            continue
        database = step["database"]
        fixture = step["fixture"]
        if database not in databases:
            name = "mrjam_synthetic_migration_" + database
            subprocess.run(["createdb", "-h", "127.0.0.1", "-p", "55432", "-U", "mrjam_synthetic", name], check=True)
            url = "postgresql://mrjam_synthetic:mrjam_synthetic_only@127.0.0.1:55432/" + name
            migrations.psql(database, migrations.source_file(root, fixture).read_text(), psql, test_url=url)
            databases[database] = (url, fixture)
        url, previous_fixture = databases[database]
        if fixture != previous_fixture:
            raise ValueError("A database must have one initial fixture for the migration sequence")
        text = migrations.sql_transaction(step, root)
        migrations.psql(database, text, psql, test_url=url)
        migrations.psql(database, text, psql, test_url=url)
    if databases:
        check = migrations.source_file(root, plan["compatibility_check"])
        environment = dict(os.environ, MRJAM_TEST_DATABASE_MAP=json.dumps({name: value[0] for name, value in databases.items()}))
        subprocess.run([sys.executable, str(check)], check=True, env=environment, timeout=1200)
    print(json.dumps({"migration_plan_checked": True, "steps": len(plan["steps"])}))


if __name__ == "__main__":
    main(Path(sys.argv[1]), sys.argv[2])
