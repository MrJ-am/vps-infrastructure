"""Version-collision projection; no corpus body or scientific answer exported.

Self-contained copy of the bound public-asset reader. No local private codebook
reference has been received, so an equality claim for that reference or its
combined digest would be fabricated. Only their presence/shape is projected.
"""
import hashlib
import json
import os
import resource
import signal
import stat
import subprocess
import sys

PREVIOUS='/nix/store/jn9rf2fgk2y6dbhdnjwkmfww3pchkyb9-nixos-system-nixos-26.05.8639.c5c4a43b0e80'
BANK='/nix/store/pdaay31fv76dxgmp1ar4xwhnbhb6fwyp-mrjam-reviewed-mrjam-qualified-artifacts-8bf05fb9065a-mateval/data/bank.json'
BANK_SHA='247e5a96f387fe87a183c07274139cd32f957b8ca54c9ca07257b6ee208bf480'
FIELDS={'selected_version_present','selected_version_unique','selected_bank_equal',
    'equal_bank_under_other_version','selected_bank_version_matches_key',
    'selected_codebook_is_object','selected_codebook_nonempty',
    'selected_digest_is_lowercase_sha256','any_corpus_present'}

def unique(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise ValueError()
        result[key]=value
    return result

def literal(value):return "'"+value.replace("'","''")+"'"

def public_bank():
    descriptor=os.open(BANK,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC|os.O_NONBLOCK)
    try:
        metadata=os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size>2*1024**2:raise ValueError()
        with os.fdopen(os.dup(descriptor),'rb') as stream:raw=stream.read(2*1024**2+1)
        if len(raw)!=metadata.st_size or hashlib.sha256(raw).hexdigest()!=BANK_SHA:raise ValueError()
        value=json.loads(raw,object_pairs_hook=unique)
        if type(value) is not dict or type(value.get('version')) is not str or not 0<len(value['version'])<=64:raise ValueError()
        return value
    finally:os.close(descriptor)

def query(bank):
    version=literal(bank['version']);document=literal(json.dumps(bank,ensure_ascii=True,separators=(',',':')))+'::jsonb'
    return ("BEGIN READ ONLY;SET LOCAL statement_timeout='5s';SET LOCAL lock_timeout='1s';SET LOCAL search_path=pg_catalog;"
        "WITH chosen AS (SELECT version,bank,codebook,digest FROM public.corpus WHERE version="+version+
        ") SELECT json_build_object("
        "'selected_version_present',EXISTS(SELECT 1 FROM chosen),"
        "'selected_version_unique',(SELECT count(*)=1 FROM chosen),"
        "'selected_bank_equal',EXISTS(SELECT 1 FROM chosen WHERE bank="+document+"),"
        "'equal_bank_under_other_version',EXISTS(SELECT 1 FROM public.corpus WHERE version<>"+version+" AND bank="+document+"),"
        "'selected_bank_version_matches_key',EXISTS(SELECT 1 FROM chosen WHERE bank->>'version'=version),"
        "'selected_codebook_is_object',EXISTS(SELECT 1 FROM chosen WHERE jsonb_typeof(codebook)='object'),"
        "'selected_codebook_nonempty',EXISTS(SELECT 1 FROM chosen WHERE jsonb_typeof(codebook)='object' AND codebook<>'{}'::jsonb),"
        "'selected_digest_is_lowercase_sha256',EXISTS(SELECT 1 FROM chosen WHERE digest~'^[0-9a-f]{64}$'),"
        "'any_corpus_present',EXISTS(SELECT 1 FROM public.corpus));ROLLBACK;")

def parse(raw):
    if len(raw)>4096:raise ValueError()
    value=json.loads(raw,object_pairs_hook=unique)
    if type(value) is not dict or set(value)!=FIELDS or any(type(v) is not bool for v in value.values()):raise ValueError()
    return value

def main():
    try:
        if len(sys.argv)!=1 or os.geteuid()!=0 or os.uname().nodename!='srv1982677' or os.path.realpath('/run/current-system')!=PREVIOUS:raise ValueError()
        resource.setrlimit(resource.RLIMIT_CORE,(0,0));resource.setrlimit(resource.RLIMIT_AS,(256*1024**2,256*1024**2))
        signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError()));signal.alarm(25)
        result=subprocess.run([PREVIOUS+'/sw/bin/runuser','-u','postgres','--',PREVIOUS+'/sw/bin/psql',
            '-X','-w','-qAt','-h','/run/postgresql','-p','5432','-d','matheval','-v','ON_ERROR_STOP=1'],
            input=query(public_bank()).encode(),stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=15,
            env={'PATH':PREVIOUS+'/sw/bin','LANG':'C','LC_ALL':'C','PGPASSFILE':'/dev/null','PGSERVICEFILE':'/dev/null',
                'PGCONNECT_TIMEOUT':'5','PGOPTIONS':'-c default_transaction_read_only=on -c statement_timeout=5000 -c search_path=pg_catalog'})
        if result.returncode:raise ValueError()
        checks=parse(result.stdout)
        value={'schema_version':1,'code':'MATHEVAL_CORPUS_VERSION_OBSERVED','checks':checks,
            'approved_codebook_reference_available':False,'codebook_equality_checked':False,
            'combined_digest_equality_checked':False,'private_values_exported':False,
            'participant_answer_session_rows_read':False,'mutation_performed':False}
        print(json.dumps(value,sort_keys=True,separators=(',',':')));return 0
    except BaseException:
        print('{"schema_version":1,"code":"MATHEVAL_CORPUS_VERSION_REFUSED"}');return 1
    finally:signal.alarm(0)

if __name__=='__main__':raise SystemExit(main())
