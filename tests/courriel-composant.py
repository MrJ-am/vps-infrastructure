"""Qualification hors production : anciennes files SQLite et messages MIME réels.
Le transport est synthétique ; aucune adresse ni aucun relais réel n'est contacté.
"""
from email import policy
from email.parser import BytesParser
import base64
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]

def verifier():
    spec=importlib.util.spec_from_file_location('ancien_courriel',ROOT/'services/mrjam-courriel/courriel.py')
    ancien=importlib.util.module_from_spec(spec);spec.loader.exec_module(ancien)
    with tempfile.TemporaryDirectory(prefix='courriel-composant-') as d:
        root=Path(d);os.chmod(root,0o700)
        cases=[]
        sujets=['MrJ.am — épreuve synthétique','é'*100,'Invitation','ASCII']
        textes=['Une épreuve.\nSecond paragraphe.','ligne '*300,'','texte\r\nfin\r']
        pieces=[None,b'\0\xffabc',b'',None]
        file=ancien.FileCourriel(root/'courriels.sqlite','sender@example.test',transport=lambda c,m:None)
        for i,(subject,text,piece) in enumerate(zip(sujets,textes,pieces)):
            key='ancien:'+str(i);file.ajouter(key,'alice@example.test',subject,text,piece)
            cases.append(dict(cle=key,subject=subject,text=text,piece=base64.b64encode(piece).decode() if piece is not None else None))
        with sqlite3.connect(file.chemin) as c:before=dict(c.execute('SELECT cle,message FROM courriels'))
        config={'host':'smtp.protonmail.ch','port':587,'username':'sender@example.test','password':'SyntheseSMTP2026Token','from_address':'sender@example.test','starttls_required':True,'certificate_verification':True}
        (root/'cas.json').write_text(json.dumps(cases));(root/'smtp.json').write_text(json.dumps(config));os.chmod(root/'smtp.json',0o600)
        (root/'public.json').write_text('{}');os.chmod(root/'public.json',0o644)
        (root/'lien.json').symlink_to(root/'smtp.json')
        (root/'journal.jsonl').write_text('');os.chmod(root/'journal.jsonl',0o600)
        def lit(s):return '"'+str(s).replace('\\','\\\\').replace('"','\\"')+'"'
        runner=root/'verifier.lisp'
        runner.write_text(f'''(load {lit(ROOT/'assemblage/charger.lisp')})
(asdf:load-system "mrjam-courriel")
(mrjam-native:initialiser-crypto {lit(os.environ.get('MRJAM_LIBCRYPTO','/lib/x86_64-linux-gnu/libcrypto.so.3'))})
(mrjam-native:initialiser-sqlite {lit(os.environ.get('MRJAM_LIBSQLITE','/lib/x86_64-linux-gnu/libsqlite3.so.0'))})
(load {lit(ROOT/'tests/courriel-composant.lisp')})
(courriel-composant:verifier {lit(root)})
''')
        subprocess.run([os.environ.get('SBCL','sbcl'),'--script',str(runner)],check=True)
        with sqlite3.connect(file.chemin) as c:
            after=dict(c.execute('SELECT cle,message FROM courriels WHERE cle LIKE \'ancien:%\''))
            assert after==before,'Un message historique a été modifié'
            wire=c.execute('SELECT message FROM courriels WHERE cle=\'nouveau:1\'').fetchone()[0]
        m=BytesParser(policy=policy.SMTP).parsebytes(wire)
        assert str(m['Subject'])=='Une épreuve — '+'é'*90
        assert str(m['Message-ID']).endswith('@mrj.am>')
        assert m.get_body(preferencelist=('plain',)).get_content()=='Texte é\nZéro 0\n'
        assert list(m.iter_attachments())[0].get_payload(decode=True)==b'\0\xffabc'
        print('SQLite historique intact ; MIME relu par la bibliothèque email Python ; aucun transport réel.')

if __name__=='__main__':verifier()
