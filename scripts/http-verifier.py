#!/usr/bin/env python3
"""Sondes HTTP bornées ; seuls des compteurs, jamais les journaux réels, sont imprimés."""
import json
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.request
import uuid


def verifier():
    debut=str(int(time.time())-1)
    marque='SONDE_HTTP_'+uuid.uuid4().hex
    def appeler(chemin):
        req=urllib.request.Request('https://vision.mrj.am'+chemin,
            headers={'Authorization':'Bearer '+marque,'Cookie':'sonde='+marque,
                     'User-Agent':marque,'Referer':'https://example.invalid/'+marque})
        try:r=urllib.request.urlopen(req,timeout=10)
        except urllib.error.HTTPError as e:r=e
        with r:return r.status
    assert appeler('/?secret='+marque)==200
    assert appeler('/mcp?secret='+marque)==401
    # Vingt petites requêtes anonymes au maximum, aucune écriture métier.
    statuts=[appeler('/mcp?secret='+marque) for _ in range(20)]
    assert 429 in statuts, 'Limitation MCP non observée : aucune conclusion DDoS'
    subprocess.run(['journalctl','--namespace=http','--sync'],check=True,capture_output=True)
    sortie=subprocess.run(['journalctl','--namespace=http','--since=@'+debut,
        '-t','http_acces','-o','cat','--no-pager','-n','200'],check=True,text=True,capture_output=True).stdout
    assert marque not in sortie, 'La sonde confidentielle apparaît dans le journal HTTP'
    lignes=[json.loads(l) for l in sortie.splitlines() if l.startswith('{')]
    lignes=[l for l in lignes if l.get('site')=='vision.mrj.am']
    assert {200,401,429} <= {l['statut'] for l in lignes}, 'Traces HTTP attendues absentes'
    assert any(l['route']=='mcp' and l['statut']==429 for l in lignes)
    assert all(set(l)=={'date','id','ip','site','methode','route','statut','octets','duree',
                       'amont','duree_amont','limite_debit','limite_connexions'} for l in lignes)
    c=Path('/etc/systemd/journald@http.conf').read_text()
    assert all(v in c for v in ['SystemMaxUse=128M','MaxRetentionSec=14day','SystemMaxFileSize=8M'])
    unite=subprocess.run(['systemctl','show','nginx','-p','LogNamespace','--value'],
        check=True,text=True,capture_output=True).stdout.strip()
    assert unite=='http'
    print(json.dumps({'journal_http':'verifie','statuts':[200,401,429],
                      'secrets_sonde_absents':True,'budget_Mio':128,'retention_max_jours':14}))


if __name__=='__main__':verifier()
