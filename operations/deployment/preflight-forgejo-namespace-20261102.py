"""Fixed read-only Forgejo namespace checks; database outputs booleans only."""
import json
import os
import resource
import subprocess
import sys

SQL = b'''BEGIN READ ONLY;
SET LOCAL statement_timeout='5s';
SET LOCAL lock_timeout='2s';
SET LOCAL search_path=pg_catalog;
WITH owner AS (SELECT id,type FROM public."user" WHERE lower_name='mrj-am'),
destinations AS (SELECT lower_name,is_private FROM public.repository
 WHERE owner_id IN (SELECT id FROM owner))
SELECT json_build_object(
 'namespace_absent',(SELECT count(*)=0 FROM owner),
 'namespace_unique_organization',(SELECT count(*)=1 AND coalesce(bool_and(type=1),false) FROM owner),
 'no_person_collision',NOT EXISTS(SELECT FROM owner WHERE type<>1),
 'no_existing_destinations',NOT EXISTS(SELECT FROM destinations),
 'private_source_visibility_compatible',NOT EXISTS(SELECT FROM destinations
   WHERE lower_name IN ('signature','matheval','mrjam-plateforme','mrjam-validation','vision') AND NOT is_private)
);
ROLLBACK;
'''
FIELDS = {'namespace_absent', 'namespace_unique_organization', 'no_person_collision',
          'no_existing_destinations', 'private_source_visibility_compatible'}


def main():
    try:
        assert len(sys.argv) == 1 and os.geteuid() == 0 and os.uname().nodename == 'srv1982677'
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        process = subprocess.run(['/run/current-system/sw/bin/psql', '-X', '-w', '-qAt',
                                  '--set=ON_ERROR_STOP=1', '--host=/run/postgresql', '--port=5432', '--dbname=forgejo'],
                                 input=SQL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                 timeout=15, check=False, user=71, group=71, extra_groups=[],
                                 env={'HOME': '/var/empty', 'USER': 'postgres', 'LOGNAME': 'postgres',
                                      'LANG': 'C', 'LC_ALL': 'C', 'TZ': 'UTC'})
        assert process.returncode == 0 and len(process.stdout) <= 2048
        value = json.loads(process.stdout)
        assert type(value) is dict and set(value) == FIELDS and all(type(x) is bool for x in value.values())
        print(json.dumps({'schema_version': 1, 'code': 'FORGEJO_NAMESPACE_OBSERVED', 'checks': value,
                          'mutation_performed': False, 'private_values_exported': False}, sort_keys=True))
        return 0
    except BaseException:
        print('{"schema_version":1,"code":"FORGEJO_NAMESPACE_UNAVAILABLE","mutation_performed":false}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
