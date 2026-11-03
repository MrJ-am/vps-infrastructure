import json,ssl,time
from pathlib import Path
p=Path('/var/lib/acme/.lego/vise.mrj.am/748661661a99cbbf91d5')
c=ssl._ssl._test_decode_cert('/var/lib/acme/vise.mrj.am/fullchain.pem')
v={'schema_version':1,'code':'VISE_CERTIFICATE_METADATA','hostname_present':('DNS','vise.mrj.am') in c.get('subjectAltName',[]),'valid_at_observation':ssl.cert_time_to_seconds(c['notBefore'])<=time.time()<ssl.cert_time_to_seconds(c['notAfter']),'retained_account_directory':Path('/var/lib/acme/.lego/accounts/a96772ab152e39f749f9').is_dir(),'retained_certificate_files':all((p/('vise.mrj.am.'+e)).is_file() for e in ['crt','key','json','issuer.crt']),'webroot_exists':Path('/var/lib/acme/acme-challenge').is_dir()}
print(json.dumps(v,sort_keys=True))
