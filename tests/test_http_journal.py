"""Le vrai Nginx doit journaliser les refus sans conserver les secrets injectés."""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time
import unittest
import urllib.error
import urllib.request

RACINE=Path(__file__).resolve().parents[1]

@unittest.skipUnless(shutil.which('nginx'), 'Nginx requis ; exécuté en CI')
class JournalHTTP(unittest.TestCase):
    def test_statuts_et_confidentialite_apres_redirection_interne(self):
        with tempfile.TemporaryDirectory() as temporaire:
            d=Path(temporaire);d.chmod(0o755)
            with socket.socket() as port_libre:
                port_libre.bind(('127.0.0.1',0));port=port_libre.getsockname()[1]
            with socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM) as journal:
                chemin=d/'journal.sock';journal.bind(str(chemin));chemin.chmod(0o666);journal.settimeout(3)
                commun=(RACINE/'lib/journal-http.conf').read_text().replace('unix:/dev/log','unix:'+str(chemin))
                (d/'nginx.conf').write_text(('user root;\n' if os.geteuid()==0 else '')+f'''
                daemon off; pid {d}/pid; error_log {d}/erreur crit;
                events {{}}
                http {{ {commun}
                  server {{ listen 127.0.0.1:{port}; server_name vision.mrj.am;
                    location / {{ return 200 'ok'; }}
                    location = /mcp {{ error_page 401 = @refus; return 401; }}
                    location @refus {{ return 401 'refus'; }}
                    location = /limite {{ return 429; }}
                    location = /panne {{ return 502; }}
                  }}
                }}''')
                cmd=['nginx','-p',str(d),'-c',str(d/'nginx.conf')]
                subprocess.run(cmd+['-t'],check=True,capture_output=True)
                proc=subprocess.Popen(cmd,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                try:
                    for _ in range(100):
                        try:
                            with socket.create_connection(('127.0.0.1',port),timeout=.1):break
                        except OSError:time.sleep(.02)
                    for chemin,statut,route in [('/',200,'accueil'),('/mcp',401,'mcp'),('/limite',429,'autre'),('/panne',502,'autre')]:
                        req=urllib.request.Request(f'http://127.0.0.1:{port}{chemin}?token=SECRET_SONDE',headers={
                            'Authorization':'Bearer SECRET_SONDE','Cookie':'session=SECRET_SONDE',
                            'User-Agent':'SECRET_SONDE','Referer':'https://example.org/SECRET_SONDE'})
                        try:r=urllib.request.urlopen(req,timeout=3)
                        except urllib.error.HTTPError as e:r=e
                        with r:self.assertEqual(r.status,statut)
                        brut=journal.recv(65536).decode()
                        self.assertNotIn('SECRET_SONDE',brut)
                        ligne=json.loads(brut[brut.index('{'):])
                        self.assertEqual(ligne['statut'],statut)
                        self.assertEqual(ligne['route'],route)
                        self.assertEqual(ligne['methode'],'GET')
                        self.assertEqual(len(ligne['id']),32)
                finally:
                    proc.terminate();proc.wait(timeout=5)

if __name__=='__main__':unittest.main()
