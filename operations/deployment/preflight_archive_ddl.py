#!/usr/bin/env python3
"""Fixed closure-image DDL classification: booleans only, no SQL export."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import resource
import signal
import stat
import sys

MODULE=Path('/nix/store/7hmdar637aj6m80vrqma57g82pgqvbc1-mrjam-mail-native-adoption-2/libexec/adopt-archive.py')
MODULE_HASH='97d43037a5eec77fb65e9f21ad36361ce2fbd67c7aa8d6d9bc0018ba32ad7aea'
SOURCE=Path('/run/mrjam-archive-mail-adoption/closure.sqlite')
TOKEN=re.compile(r"(?P<quoted>'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"|`(?:[^`]|``)*`|\[[^\]]*\])|(?P<comment>--[^\r\n]*(?:\r?\n|$)|/\*.*?\*/)|(?P<word>[A-Za-z_][A-Za-z_0-9$]*)|(?P<number>[0-9]+(?:\.[0-9]*)?(?:[eE][+-]?[0-9]+)?|\.[0-9]+(?:[eE][+-]?[0-9]+)?)|(?P<operator>!=|<>|<=|>=|==|<<|>>|\|\||->>|->|[(),.;=<>+*/%&|~\-])",re.S)


def sql_tokens(sql,fold_words=False):
    if sql is None:return None
    if type(sql) is not str or len(sql)>8192:raise ValueError()
    result=[];position=0
    while position<len(sql):
        if sql[position] in ' \t\r\n\f\v':position+=1;continue
        token=TOKEN.match(sql,position)
        if token is None:raise ValueError()
        kind=token.lastgroup;value=token.group()
        result.append((kind,value.lower() if fold_words and kind=='word' else value))
        position=token.end()
    return tuple(result)


def normalized(objects,fold=False):
    return [(kind,name,table,sql_tokens(sql,fold)) for kind,name,table,sql in objects]


def classify(module,raw):
    db=module.connection(raw)
    try:
        actual=module.objects(db)
        candidates=[]
        for native in (False,True):
            for hashes in (0,1,2):
                for marker in (None,'closure'):
                    model=module.reference(native=native,hashes=hashes,marker=marker)
                    try:
                        objects=module.objects(model)
                        if [row[:3] for row in actual]==[row[:3] for row in objects]:
                            candidates.append((objects,db.execute('PRAGMA table_info(courriels)').fetchall()==model.execute('PRAGMA table_info(courriels)').fetchall(),
                                db.execute('PRAGMA table_info(fermetures)').fetchall()==model.execute('PRAGMA table_info(fermetures)').fetchall()))
                    finally:model.close()
        result={'matching_object_set':bool(candidates),'full_whitespace_token_match':False,
                'full_wordcase_token_match':False,'mail_columns_match_same_model':False,
                'closure_columns_match_same_model':False}
        roles={'mail_table':lambda r:r[0]=='table' and r[1]=='courriels',
               'closure_table':lambda r:r[0]=='table' and r[1]=='fermetures',
               'indexes':lambda r:r[0]=='index'}
        for role in roles:
            result[role]={'exact_ddl_match':False,'whitespace_token_match':False,'wordcase_token_match':False}
        for objects,mail_columns,closure_columns in candidates:
            result['mail_columns_match_same_model'] |= mail_columns
            result['closure_columns_match_same_model'] |= closure_columns
            result['full_whitespace_token_match'] |= normalized(actual)==normalized(objects)
            result['full_wordcase_token_match'] |= normalized(actual,True)==normalized(objects,True)
            for role,select in roles.items():
                observed=[row for row in actual if select(row)];expected=[row for row in objects if select(row)]
                result[role]['exact_ddl_match'] |= observed==expected
                result[role]['whitespace_token_match'] |= normalized(observed)==normalized(expected)
                result[role]['wordcase_token_match'] |= normalized(observed,True)==normalized(expected,True)
        return result
    finally:db.close()


def collect():
    if hashlib.sha256(MODULE.read_bytes()).hexdigest()!=MODULE_HASH:raise ValueError()
    spec=importlib.util.spec_from_file_location('closed_archive_ddl',MODULE)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    parent=SOURCE.parent.lstat()
    if not stat.S_ISDIR(parent.st_mode) or parent.st_uid!=943 or stat.S_IMODE(parent.st_mode)!=0o700:raise ValueError()
    fd=os.open(SOURCE,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        item=os.fstat(fd)
        if item.st_uid!=0 or item.st_gid!=943 or stat.S_IMODE(item.st_mode)!=0o440 or item.st_nlink!=1:raise ValueError()
        raw=module.read_fd(fd,module.MAX_SOURCE)
    finally:os.close(fd)
    return {'schema_version':1,'code':'ARCHIVE_DDL_CLASSIFIED','checks':classify(module,raw),
            'private_values_exported':False,'mutation_performed':False}


def main():
    if len(sys.argv)!=1 or os.geteuid()!=0:return 64
    resource.setrlimit(resource.RLIMIT_CORE,(0,0));resource.setrlimit(resource.RLIMIT_AS,(768*1024**2,768*1024**2))
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError()));signal.alarm(30)
    try:value=collect();code=0
    except Exception:value={'schema_version':1,'code':'ARCHIVE_DDL_UNAVAILABLE','private_values_exported':False,'mutation_performed':False};code=1
    finally:signal.alarm(0)
    print(json.dumps(value,sort_keys=True,separators=(',',':')))
    return code


if __name__=='__main__':raise SystemExit(main())
