"""Fixed local-only pipe from corpus 0.3.0 to the qualified pure Rust classifier.

No corpus, codebook or SQL result is printed or persisted. Only a closed map of
booleans is emitted. Requires the returned previous generation and exact ELF.
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
BINARY='/nix/store/anvdal9pag7qh6w13cn88mw1pdlyiky2-mrjam-mateval-corpus-classifier-1/bin/mrjam-mateval-corpus-classifier'
BINARY_SHA='d1a4d2419c025b202a21c492973d2864f882a07fb272e0682bce2dbbaffc9a59'
MAXIMUM=5*1024**2
FIELDS={'raw_json_equal','typed_deserialization_accepted','typed_validation_accepted',
 'typed_json_equal','version_equal','question_count_equal','question_ids_and_order_equal',
 'question_families_equal','question_levels_equal','question_domains_equal',
 'question_statements_equal','production_ids_and_order_equal','production_contents_equal',
 'extra_root_fields_present','extra_question_fields_present','extra_production_fields_present'}
SQL="""BEGIN READ ONLY;
SET LOCAL statement_timeout='5s';SET LOCAL lock_timeout='1s';
SET LOCAL search_path=pg_catalog;SET LOCAL ROLE matheval_app;
SELECT CASE WHEN jsonb_typeof(bank)='object' AND octet_length(bank::text)<=5242880
 THEN bank::text ELSE NULL END FROM public.corpus WHERE version='0.3.0' LIMIT 2;
ROLLBACK;
"""

def unique(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise ValueError()
        result[key]=value
    return result

def result(raw):
    if len(raw)>4096:raise ValueError()
    value=json.loads(raw,object_pairs_hook=unique)
    if type(value) is not dict or set(value)!={'schema_version','code','checks','corpus_values_exported','codebook_read','mutation_performed'}:raise ValueError()
    if type(value['schema_version']) is not int or value['schema_version']!=1 or value['code']!='MATHEVAL_TYPED_CORPUS_CLASSIFIED':raise ValueError()
    if type(value['checks']) is not dict or set(value['checks'])!=FIELDS or any(type(v) is not bool for v in value['checks'].values()):raise ValueError()
    if any(value[k] is not False for k in ('corpus_values_exported','codebook_read','mutation_performed')):raise ValueError()
    return value

def classifier_verified():
    descriptor=os.open(BINARY,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC|os.O_NONBLOCK)
    try:
        metadata=os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size>8*1024**2:raise ValueError()
        with os.fdopen(os.dup(descriptor),'rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
        if digest!=BINARY_SHA:raise ValueError()
    finally:os.close(descriptor)

def main():
    try:
        if len(sys.argv)!=1 or os.geteuid()!=0 or os.uname().nodename!='srv1982677' or os.path.realpath('/run/current-system')!=PREVIOUS:raise ValueError()
        resource.setrlimit(resource.RLIMIT_CORE,(0,0));resource.setrlimit(resource.RLIMIT_AS,(256*1024**2,256*1024**2))
        signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError()));signal.alarm(25)
        classifier_verified()
        process=subprocess.run([PREVIOUS+'/sw/bin/runuser','-u','postgres','--',PREVIOUS+'/sw/bin/psql',
            '-X','-w','-qAt','-h','/run/postgresql','-p','5432','-d','matheval','-v','ON_ERROR_STOP=1'],
            input=SQL.encode(),stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=12,
            env={'PATH':PREVIOUS+'/sw/bin','LANG':'C','LC_ALL':'C','PGPASSFILE':'/dev/null','PGSERVICEFILE':'/dev/null',
                'PGCONNECT_TIMEOUT':'5','PGOPTIONS':'-c default_transaction_read_only=on -c statement_timeout=5000 -c search_path=pg_catalog'})
        if process.returncode or not process.stdout or len(process.stdout)>MAXIMUM:raise ValueError()
        classified=subprocess.run([BINARY],input=process.stdout,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
            timeout=5,env={'LANG':'C','LC_ALL':'C'})
        if classified.returncode:raise ValueError()
        print(json.dumps(result(classified.stdout),sort_keys=True,separators=(',',':')));return 0
    except BaseException:
        print('{"schema_version":1,"code":"MATHEVAL_TYPED_CORPUS_PROBE_REFUSED"}');return 1
    finally:signal.alarm(0)

if __name__=='__main__':raise SystemExit(main())
