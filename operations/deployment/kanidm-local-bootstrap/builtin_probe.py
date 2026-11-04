"""Only two builtin UUIDs, read-only SQLite projection, boolean output only."""
import datetime
import json
import os
from pathlib import Path
import resource
import sqlite3
import stat
import sys
import time

PREVIOUS='/nix/store/jn9rf2fgk2y6dbhdnjwkmfww3pchkyb9-nixos-system-nixos-26.05.8639.c5c4a43b0e80'
DATABASE=Path('/var/lib/kanidm/kanidm.db')
BUILTINS={'admin':'00000000-0000-0000-0000-000000000000','idm_admin':'00000000-0000-0000-0000-000000000018'}


def require(value):
    if not value:raise RuntimeError('BUILTIN_STATE_REFUSED')


def observe(path=DATABASE):
    info=path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_nlink==1 and os.path.realpath(path)==str(path))
    deadline=time.monotonic()+5
    connection=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=3)
    try:
        connection.execute('PRAGMA query_only=ON')
        connection.execute('PRAGMA trusted_schema=OFF')
        connection.set_progress_handler(lambda: int(time.monotonic()>deadline),1000)
        connection.execute('BEGIN')
        result={}
        for name,uid in BUILTINS.items():
            rows=connection.execute('SELECT substr(idl,1,1025),length(idl) FROM idx_eq_uuid WHERE key=? LIMIT 2',(uid,)).fetchall()
            require(len(rows)==1 and 0<rows[0][1]<=1024)
            index=json.loads(rows[0][0])
            require(type(index) is dict and set(index)=={'t'} and type(index['t']) is dict and set(index['t'])=={'s'})
            ids=index['t']['s']
            require(type(ids) is list and len(ids)==1 and type(ids[0]) is int and 0<ids[0]<2**63)
            # Only selected non-secret identity fields and credential-presence
            # booleans leave SQLite. Neither credential hashes nor keys are read
            # into Python; no unfiltered entry or table scan is performed.
            rows=connection.execute("""SELECT
              json_extract(data,'$.ent.V3.attrs.uuid.UU'),
              json_extract(data,'$.ent.V3.attrs.name.N8'),
              json_extract(data,'$.ent.V3.attrs.class.I8'),
              json_type(data,'$.ent.V3.attrs.passkeys') IS NOT NULL,
              json_type(data,'$.ent.V3.attrs.attested_passkeys') IS NOT NULL,
              json_extract(data,'$.ent.V3.attrs.account_expire.DT')
              FROM id2entry WHERE id=? LIMIT 2""",(ids[0],)).fetchall()
            require(len(rows)==1)
            actual_uid,actual_name,classes,passkeys,attested,expiry=rows[0]
            require(json.loads(actual_uid)==[uid] and json.loads(actual_name)==[name])
            classes=json.loads(classes)
            require(type(classes) is list and all(type(item) is str for item in classes))
            expired=False
            if expiry is not None:
                values=json.loads(expiry)
                require(type(values) is list and len(values)==1 and type(values[0]) is str and len(values[0])<=64)
                date=datetime.datetime.fromisoformat(values[0].replace('Z','+00:00'))
                require(date.tzinfo is not None)
                expired=date.timestamp()<=time.time()
            service='service_account' in classes and 'person' not in classes
            result[name]={'builtin_identity_matches':True,'service_account_not_person':service,
                          'passkeys_present':bool(passkeys),'attested_passkeys_present':bool(attested),'disabled':expired,
                          'eligible_for_fixed_recovery':service and expired and not passkeys and not attested}
        return {'schema_version':1,'read_only':True,'credential_material_exported':False,
                'builtin_states':result,'both_eligible':all(item['eligible_for_fixed_recovery'] for item in result.values())}
    finally:connection.close()


def main():
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    require(len(sys.argv)==1 and os.geteuid()==0 and os.path.realpath('/run/current-system')==PREVIOUS)
    info=DATABASE.lstat()
    require((info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode))==(983,983,0o600))
    return observe()


if __name__=='__main__':
    try:print(json.dumps(main(),sort_keys=True,separators=(',',':')))
    except Exception:
        print('{"schema_version":1,"code":"BUILTIN_STATE_REFUSED"}')
        raise SystemExit(1)
