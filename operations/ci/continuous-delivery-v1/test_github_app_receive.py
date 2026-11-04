from pathlib import Path
import base64,importlib.util,json,os,stat,subprocess,tempfile,unittest
spec=importlib.util.spec_from_file_location('receiver',Path(__file__).with_name('github-app-receive.py'))
R=importlib.util.module_from_spec(spec);spec.loader.exec_module(R)
class ReceiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        p=subprocess.run([R.OPENSSL,'genpkey','-algorithm','RSA','-pkeyopt','rsa_keygen_bits:2048'],
                         stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,check=True,timeout=15)
        cls.value={'app_id':123,'owner_id':12571490,'slug':'synthetic-app','permissions':dict(R.PERMISSIONS),'private_key':p.stdout.decode()}
    def test_real_rsa_signature_and_bounded_expiry(self):
        token=R.jwt(self.value);header,payload,signature=token.split('.')
        decode=lambda s:base64.urlsafe_b64decode(s+'='*(-len(s)%4))
        self.assertEqual(json.loads(decode(header)),{'alg':'RS256','typ':'JWT'})
        claims=json.loads(decode(payload));self.assertEqual(claims['iss'],123)
        self.assertEqual(claims['exp']-claims['iat'],600)
        with tempfile.TemporaryDirectory() as name:
            path=Path(name)
            pub=subprocess.run([R.OPENSSL,'pkey','-pubout'],input=self.value['private_key'].encode(),stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,check=True)
            (path/'pub.pem').write_bytes(pub.stdout);(path/'sig').write_bytes(decode(signature))
            result=subprocess.run([R.OPENSSL,'dgst','-sha256','-verify',str(path/'pub.pem'),'-signature',str(path/'sig')],input=(header+'.'+payload).encode(),stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
            self.assertEqual(result.returncode,0)
    def test_owner_permissions_and_key_refusals(self):
        for field,value in [('owner_id',1),('permissions',{'administration':'write'}),('app_id',True),('slug','../escape')]:
            with self.assertRaises(R.Refused):R.checked({**self.value,field:value})
        with self.assertRaises(R.Refused):R.jwt({**self.value,'private_key':'A'*1500})
    def test_private_install_once(self):
        with tempfile.TemporaryDirectory() as name:
            directory=Path(name)/'credentials';R.install(directory,self.value)
            self.assertEqual(stat.S_IMODE(directory.stat().st_mode),0o700)
            self.assertEqual(stat.S_IMODE((directory/'app-credentials.json').stat().st_mode),0o400)
            with self.assertRaises(FileExistsError):R.install(directory,self.value)
    def test_symlink_directory_refused(self):
        with tempfile.TemporaryDirectory() as name:
            target=Path(name)/'target';target.mkdir(mode=0o700)
            link=Path(name)/'link';link.symlink_to(target)
            with self.assertRaises(R.Refused):R.install(link,self.value)

if __name__=='__main__':unittest.main()
