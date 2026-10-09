"""PKI synthétique privée : certificats admis et erreurs TLS/nom pour Keycloak."""
import argparse
import datetime
import ipaddress
from pathlib import Path
import subprocess
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

p=argparse.ArgumentParser(description=__doc__);p.add_argument('--destination',required=True);a=p.parse_args()
r=Path(a.destination);r.mkdir(mode=0o700,parents=True,exist_ok=True)
maintenant=datetime.datetime.now(datetime.timezone.utc)
for nom,ip in [('correct','127.0.0.1'),('autre','127.0.0.1'),('nom-invalide','192.0.2.1')]:
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    sujet=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,ip)])
    cert=(x509.CertificateBuilder().subject_name(sujet).issuer_name(sujet).public_key(key.public_key())
        .serial_number(x509.random_serial_number()).not_valid_before(maintenant-datetime.timedelta(minutes=1))
        .not_valid_after(maintenant+datetime.timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address(ip))]),critical=False)
        .sign(key,hashes.SHA256()))
    certificat=r/(nom+'.pem');certificat.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    cle=r/(nom+'.key');cle.write_bytes(key.private_bytes(serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,serialization.NoEncryption()));cle.chmod(0o600)
    if nom!='autre':
        subprocess.run(['keytool','-importcert','-noprompt','-alias',nom,'-file',str(certificat),
            '-keystore',str(r/'confiance.p12'),'-storetype','PKCS12','-storepass','qualification-locale'],
            check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
(r/'confiance.p12').chmod(0o600)
