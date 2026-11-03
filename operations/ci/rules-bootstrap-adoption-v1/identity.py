"""Resolve only the retained, uniquely attested SSO owner, inside the VPS."""
import re
import sso


class Refused(RuntimeError):
    pass


def require(value):
    if not value:
        raise Refused("HUMAN_IDENTITY_REFUSED")


def owner(bootstrap):
    subject=sso.subject_from_binding()
    query=sso.query(subject)
    require(query.count(b"BEGIN READ ONLY;")==1 and query.endswith(b"ROLLBACK;\n"))
    query=query.replace(b"BEGIN READ ONLY;",b"BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;")
    # Both statements share the same read-only snapshot. The first is exactly
    # the already-qualified eight checks; the second reveals only the unique
    # eligible account ID to this process, never to public output or argv.
    query=query[:-len(b"ROLLBACK;\n")]+b'''SELECT id FROM public."user"
WHERE lower_name IN ('mrjam','mrjam-admin');
ROLLBACK;
'''
    raw=bootstrap.command([bootstrap.PSQL,"-X","-w","-qAt","-h","/run/postgresql",
        "-d","forgejo","-v","ON_ERROR_STOP=1"],query)
    rows=raw.splitlines()
    require(len(rows)==2 and len(rows[0])<=2048 and all(sso.parse_result(rows[0]).values()))
    require(re.fullmatch(rb"[1-9][0-9]{0,18}",rows[1]) and int(rows[1])<=2**63-1)
    return int(rows[1])
