from pathlib import Path
import subprocess,json,hashlib
OLD=Path('/nix/store/phi68cwg38madbq8p805yvrsyry8g8wr-nixos-system-srv1982677-26.05pre-git')
NEW=Path('/nix/store/g1l3zif8rwndmdcyc1vylwasaxds9iia-nixos-system-srv1982677-26.05pre-git')
def inventory(path):
 p=subprocess.Popen(['zstd','-d','-c',str(path.resolve())],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL);s=p.stdout;out={}
 while True:
  h=s.read(110)
  if not h:break
  assert len(h)==110 and h[:6] in [b'070701',b'070702']
  values=[int(h[i:i+8],16) for i in range(6,110,8)]
  ino,mode,uid,gid,nlink,mtime,size,devmajor,devminor,rdevmajor,rdevminor,namesize,check=values
  assert 0<namesize<65536 and size<1024**3
  name=s.read(namesize);assert name[-1:]==b'\0';name=name[:-1].decode();s.read(-(110+namesize)%4)
  data=s.read(size);assert len(data)==size;s.read(-size%4)
  if name=='TRAILER!!!':
   s.read();break
  assert name not in out
  out[name]={'mode':mode,'uid':uid,'gid':gid,'nlink':nlink,'bytes':size,'sha256':hashlib.sha256(data).hexdigest()}
  if mode & 0o170000==0o120000:out[name]['target']=data.decode()
 assert p.wait()==0
 return out
a=inventory(OLD/'initrd');b=inventory(NEW/'initrd')
v={'old_entries':len(a),'new_entries':len(b),'changed':{k:{'old':a[k],'new':b[k]} for k in a.keys()&b.keys() if a[k]!=b[k]},'removed':sorted(a.keys()-b.keys()),'added':sorted(b.keys()-a.keys())}
Path('.local/deployment-20261101/ci-initrd-Q-delta.json').write_text(json.dumps(v,indent=2,sort_keys=True)+'\n');print(json.dumps({'changed':list(v['changed']),'added':v['added'],'removed':v['removed'],'entries':[len(a),len(b)]}))
