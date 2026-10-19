"""Fixed Nextcloud SSO payload over the existing infrastructure SSH channel."""
import io,json,os,pathlib,re,shlex,subprocess,tarfile
ROOT=pathlib.Path(__file__).resolve().parents[1]

def main():
    assert os.environ.get('GITHUB_ACTIONS')=='true' and os.environ.get('GITHUB_REF')=='refs/heads/main'
    phase=os.environ['MRJAM_OPERATION'].removeprefix('nextcloud-sso-')
    assert phase in ('preparer','deployer','retour','diagnostic')
    rev=json.loads((ROOT/'operations/nextcloud-sso-candidat.json').read_text())['revision_sources']
    assert re.fullmatch('[a-f0-9]{40}',rev)
    remote='/root/mrjam-corrections/nextcloud-sso/'+rev
    if phase=='preparer':
        subprocess.run(['git','fetch','--depth=1','origin',rev],cwd=ROOT,check=True,stdout=subprocess.DEVNULL)
        data=io.BytesIO()
        with tarfile.open(fileobj=data,mode='w:gz') as archive:
            names=['assemblage/nextcloud-sso/'+n for n in ['promote.py','client.py','module.nix','target.json','qualification-locale.json']]+['scripts/kanidm-api-privee.py']
            for name in names:
                content=subprocess.check_output(['git','show',rev+':'+name],cwd=ROOT)
                if name.endswith('qualification-locale.json'):
                    proof=json.loads(content);assert proof['realMfaPkceEs256'] and proof['existingAccountPreserved'] and proof['localPasswordPostDenied']
                entry=tarfile.TarInfo('payload/'+pathlib.Path(name).name);entry.size=len(content);entry.mode=0o600
                archive.addfile(entry,io.BytesIO(content))
        subprocess.run(['sh',str(ROOT/'scripts/connect.sh'),'umask 077; mkdir -p '+remote+'; tar -xzf - -C '+remote],input=data.getvalue(),check=True)
    command='python3 -B '+remote+'/payload/promote.py '+phase+' '+rev
    # Strip nix-shell development variables when operating the installed PHP CLI.
    subprocess.run(['sh',str(ROOT/'scripts/connect.sh'),'nix-shell -p python3 --run '+shlex.quote(command)],check=True)

if __name__=='__main__':main()
