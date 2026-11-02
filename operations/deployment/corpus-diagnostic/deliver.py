"""Import only the exact qualified classifier closure, without activation."""
import hashlib,json,os,resource,signal,subprocess,sys,tempfile
PREVIOUS='/nix/store/jn9rf2fgk2y6dbhdnjwkmfww3pchkyb9-nixos-system-nixos-26.05.8639.c5c4a43b0e80'
MANIFEST={'store_paths': ['/nix/store/4fhm41clh7s82xgb3jdnpll1axi9zqgq-xgcc-15.3.0-libgcc', '/nix/store/hl2q8nksy0m8qgh3hzvd24rhill1rpix-libunistring-1.4.2', '/nix/store/scgsymw7hbvk6hh2cgbdz906iv4v5y9z-libidn2-2.3.8', '/nix/store/dphsh3jff8w6n9p3xbfmkia5krqwv52f-glibc-2.42-103', '/nix/store/anvdal9pag7qh6w13cn88mw1pdlyiky2-mrjam-mateval-corpus-classifier-1'], 'size': 38429920, 'sha256': 'f268a266ab6412adbaaef1c781e756c4d8144974616079a16dad0dfe31746fdd'}

def main():
    try:
        if len(sys.argv)!=1 or os.geteuid()!=0 or os.uname().nodename!='srv1982677' or os.path.realpath('/run/current-system')!=PREVIOUS:raise ValueError()
        os.umask(0o077)
        resource.setrlimit(resource.RLIMIT_CORE,(0,0))
        signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError()))
        signal.alarm(180)
        capacity=os.statvfs('/nix/store')
        if capacity.f_bavail*capacity.f_frsize<1024**3:raise ValueError()
        with tempfile.TemporaryFile(mode='w+b',dir='/run') as stream:
            digest=hashlib.sha256();total=0
            while total<=MANIFEST['size']:
                chunk=sys.stdin.buffer.read(min(1024**2,MANIFEST['size']-total+1))
                if not chunk:break
                total+=len(chunk)
                if total>MANIFEST['size']:raise ValueError()
                digest.update(chunk);stream.write(chunk)
            if total!=MANIFEST['size'] or digest.hexdigest()!=MANIFEST['sha256']:raise ValueError()
            stream.flush();stream.seek(0)
            env={'LANG':'C','LC_ALL':'C','NIX_PATH':''}
            r=subprocess.run([PREVIOUS+'/sw/bin/nix-store','--import'],stdin=stream,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=90,env=env)
            if r.returncode:raise ValueError()
            paths=r.stdout.decode('ascii').splitlines()
            if len(paths)!=len(set(paths)) or set(paths)!=set(MANIFEST['store_paths']):raise ValueError()
            r=subprocess.run([PREVIOUS+'/sw/bin/nix-store','--verify-path',*MANIFEST['store_paths']],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=45,env=env)
            if r.returncode:raise ValueError()
        print(json.dumps({'schema_version':1,'code':'CORPUS_CLASSIFIER_IMPORTED','store_paths_verified':5,'application_activation':False,'database_access':False,'secret_content_read':False},sort_keys=True))
        return 0
    except BaseException:
        print('{"schema_version":1,"code":"CORPUS_CLASSIFIER_IMPORT_REFUSED"}')
        return 1
    finally:signal.alarm(0)

if __name__=='__main__':raise SystemExit(main())
