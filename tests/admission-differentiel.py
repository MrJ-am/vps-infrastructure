"""Règles de consentement/admission comparées au validateur Python historique."""
import ast
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
def verifier():
    spec=importlib.util.spec_from_file_location('courriel_reference',ROOT/'services/mrjam-courriel/courriel.py')
    courriel=importlib.util.module_from_spec(spec);spec.loader.exec_module(courriel)
    path=ROOT/'services/mrjam-admission/admission.py';tree=ast.parse(path.read_text())
    nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='verifier']
    namespace={'re':re,'adresse':courriel.adresse};exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),'exec'),namespace)
    cases=[];base={'invitation':'a'*43,'notice':'notice-test','courriel':'Alice@Example.test','pays':'France','age':'majeur','parent':'','pseudonyme':'Pseudo'}
    def cas(p):
        try:result=namespace['verifier'](p)
        except (ValueError,TypeError,AttributeError):result=None
        cases.append({'input':p,'result':result})
    for country in ['France','FR','FRANÇAISE','francais',' Belgium ','\xa0France\xa0','France\n','F']:
        for age in ['moins15','15a17','majeur','inconnu']:
            for parent in ['', 'Parent@Example.test','alice@example.test']:cas({**base,'pays':country,'age':age,'parent':parent})
    for key in base:
        for value in [None,True,0,'', 'x'*101, 'x\x00y']:
            cas({**base,key:value})
    cas({**base,'acteur':'admin'});cas(None);cas([])
    def lit(s):return '"'+str(s).replace('\\','\\\\').replace('"','\\"')+'"'
    with tempfile.TemporaryDirectory(prefix='admission-differentiel-') as d:
        fixture=Path(d)/'cas.json';fixture.write_text(json.dumps(cases))
        runner=Path(d)/'verifier.lisp';runner.write_text(f'''(load {lit(ROOT/'assemblage/charger.lisp')})
(asdf:load-system "vision/admission")
(load {lit(ROOT/'tests/admission-differentiel.lisp')})
(admission-differentiel:verifier {lit(fixture)})
''')
        subprocess.run([os.environ.get('SBCL','sbcl'),'--script',str(runner)],check=True)
if __name__=='__main__':verifier()
