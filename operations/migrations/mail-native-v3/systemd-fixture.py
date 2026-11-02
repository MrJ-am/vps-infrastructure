"""Invented mail only; real staging helper and systemd adoption units."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys

sys.path.insert(0,'/etc/staging-helper')
import stage_adoption
spec=importlib.util.spec_from_file_location('adopt','/etc/mail-v3/adopt.py')
adopt=importlib.util.module_from_spec(spec);spec.loader.exec_module(adopt)
TARGET=Path('/var/lib/mrjam-vision-archive/courriels.sqlite')
LEGACY=Path('/var/lib/mrjam-metier')
PROOF=Path('/run/invented-archive-v3-proof.json')
MESSAGE=b'INVENTED_OPAQUE_MAIL\x00\xff\r\n'


def source(relative,mode,scope):
    path=LEGACY/relative
    path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    path.unlink(missing_ok=True)
    with sqlite3.connect(path) as db:
        if scope=='unused':db.execute('CREATE TABLE invented(value TEXT)')
        else:
            db.executescript(adopt.schema('native-mail.sql'))
            db.execute('ALTER TABLE courriels ADD COLUMN empreinte TEXT')
            db.execute('ALTER TABLE courriels ADD COLUMN empreinte_metier TEXT')
            db.execute('INSERT INTO courriels VALUES(?,?,?,?,?,?,?,?,?,?)',
                ('invented-shared',MESSAGE,10,'attente',2 if mode!='collision' or scope!='global' else 3,40,None,'invented-error',hashlib.sha256(MESSAGE).hexdigest(),'c'*64))
            if scope=='closure':
                marker=adopt.schema('closure-markers.sql')
                if mode=='whitespace':marker=marker.replace('fermetures(', 'fermetures (\n\t').replace(',', ',\n\t')
                if mode=='constraint':marker=marker.replace('sujet TEXT PRIMARY KEY',"sujet TEXT PRIMARY KEY CHECK(sujet != 'invented-forbidden')")
                if mode=='default':marker=marker.replace('terminee INTEGER','terminee INTEGER DEFAULT 0')
                db.executescript(marker)
                db.execute("INSERT INTO fermetures VALUES('invented-subject',20,30)")
    path.chmod(0o600);os.chown(path,984,984)


def prepare(mode):
    assert mode in ('whitespace','exact','constraint','default','collision')
    for name in stage_adoption.PROFILES:shutil.rmtree(Path('/run')/name,ignore_errors=True)
    source('admission/admissions.sqlite',mode,'unused')
    source('admission/courriels.sqlite',mode,'unused')
    source('cycle/courriels.sqlite',mode,'cycle')
    source('fermeture/courriels.sqlite',mode,'closure')
    source('courriel/file.sqlite',mode,'global')
    stage_adoption.prepare()
    expected={str(LEGACY/relative):hashlib.sha256((LEGACY/relative).read_bytes()).hexdigest()
        for relative in ('cycle/courriels.sqlite','fermeture/courriels.sqlite','courriel/file.sqlite')}
    Path('/run/invented-source-hashes.json').write_text(json.dumps(expected))


def verify():
    item=TARGET.stat()
    assert item.st_uid==item.st_gid==943 and item.st_mode&0o777==0o600 and item.st_nlink==1
    with sqlite3.connect('file:'+str(TARGET)+'?mode=ro',uri=True) as db:
        assert db.execute('SELECT * FROM courriels').fetchall()==[
            ('invented-shared',MESSAGE,10,'attente',2,40,None,'invented-error',hashlib.sha256(MESSAGE).hexdigest(),None,'c'*64)]
        assert db.execute('SELECT * FROM fermetures').fetchall()==[('invented-subject',20,30)]
    for path,digest in json.loads(Path('/run/invented-source-hashes.json').read_text()).items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest
    current={'inode':item.st_ino,'sha256':hashlib.sha256(TARGET.read_bytes()).hexdigest()}
    if PROOF.exists():assert json.loads(PROOF.read_text())==current
    else:PROOF.write_text(json.dumps(current))


if sys.argv[1]=='prepare':prepare(sys.argv[2])
elif sys.argv[1]=='verify':verify()
else:raise SystemExit(64)
