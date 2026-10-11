"""Ancien validateur Python en lecture seule ; bibliothèque ASDF en image neuve."""
import ast
import datetime
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import uuid

ROOT=Path(__file__).resolve().parents[1]

def verifier():
    source=ROOT/'services/vision-gestion/server.py'
    tree=ast.parse(source.read_text())
    nodes=[n for n in tree.body if isinstance(n,ast.Assign) or isinstance(n,ast.FunctionDef) and n.name=='verifier']
    reference={'re':re,'uuid':uuid,'datetime':datetime}
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(source),'exec'),reference)
    cases=[]
    def cas(op,p):
        try: reference['verifier'](op,p);ok=True
        except (ValueError,TypeError):ok=False
        cases.append(dict(op=op,p=p,ok=ok))
    for op in reference['CHAMPS']:
        for p in [{},{'utilisateur':'alice','version':1},{'utilisateur':'alice','version':True},{'debut':0},{'debut':100001},{'acteur':'admin'},[],None]:cas(op,p)
    for day in ['2028-02-29','2027-02-29','2028-01-01','20280101','2028-W01-1','2028W011','2028-W01','2028-W54-1','0001-01-01','9999-12-31']:
        for time in ['12','120030','12:00','12:00:00','24:00:00','12:00:00.123456','12:00:00,1']:
            for zone in ['Z','+0100','+01:00','+23:59:59','+24:00','+00:99','+0060','']:
                cas('creer_invitation',dict(intitule='Invitation synthétique',maximum=1,expire_a=day+'T'+time+zone))
    for k,values in {'administrateur':[True,False,'true',0,None],'quota_octets':[0,1,1000000000,1000000001,1.0],'version':[0,1,2**53-1,2**53,1.0],
                     'utilisateur':['alice','bob_2','x.y-z','é',"alice';SELECT",'', 'x'*65]}.items():
        for v in values:cas('modifier_compte',{'utilisateur':'alice','version':1,k:v})
    for title in ['\xa0','\xa0é\xa0','x'*100,'x'*101,'a\x00b','😀']:
        cas('creer_invitation',dict(intitule=title,maximum=1,expire_a='2028-01-01T12:00:00Z'))
    def lit(s):return '"'+str(s).replace('\\','\\\\').replace('"','\\"')+'"'
    with tempfile.TemporaryDirectory(prefix='gestion-differentiel-') as d:
        fixture=Path(d)/'cas.json';fixture.write_text(json.dumps(cases))
        runner=Path(d)/'verifier.lisp'
        runner.write_text(f'''(load {lit(ROOT/'assemblage/charger.lisp')})
(asdf:load-system "vision/administration")
(load {lit(ROOT/'tests/gestion-differentiel.lisp')})
(gestion-differentiel:verifier {lit(fixture)})
''')
        subprocess.run([os.environ.get('SBCL','sbcl'),'--script',str(runner)],check=True)

if __name__=='__main__':verifier()
