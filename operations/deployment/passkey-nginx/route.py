#!/usr/bin/env python3
"""One sealed, temporary same-origin route; no application generation switch."""
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("immutable_nginx_code",ROOT/"preflight_passkey_nginx.py")
P=importlib.util.module_from_spec(spec)
spec.loader.exec_module(P)
WORK=Path("/run/mrjam-passkey-nginx-route")
TEMPORARY=WORK/"nginx.conf"
DROPIN=Path("/run/systemd/system/nginx.service.d/90-mrjam-passkey-portal.conf")
SOCKET=Path("/run/mrjam-kanidm-passkey-portal/http.sock")
TTL=900
LOCATION=b'''
  location ^~ /_mrjam-worker-provision/ {
    access_log off;
    error_log /dev/null crit;
    client_max_body_size 32k;
    client_body_buffer_size 32k;
    proxy_request_buffering off;
    proxy_buffering off;
    proxy_http_version 1.1;
    proxy_set_header Host log.mrj.am;
    proxy_set_header Connection close;
    proxy_set_header Cookie "";
    proxy_set_header Authorization "";
    proxy_set_header X-Forwarded-Proto https;
    proxy_connect_timeout 2s;
    proxy_send_timeout 5s;
    proxy_read_timeout 180s;
    proxy_pass http://unix:/run/mrjam-kanidm-passkey-portal/http.sock;
  }
'''


class Refused(Exception):pass
class Stopped(BaseException):pass


def require(value):
    if not value:raise Refused()


def encode(value):
    return (json.dumps(value,sort_keys=True,separators=(",",":"))+"\n").encode()


def digest(raw):return hashlib.sha256(raw).hexdigest()


def binding():
    item=json.loads(ROOT.joinpath("binding.json").read_bytes())
    require(set(item)=={"generation","configuration","configuration_sha256","executable","executable_sha256",
                       "unit","unit_sha256","tls_server_sha256"})
    for key in ("configuration_sha256","executable_sha256","unit_sha256","tls_server_sha256"):
        require(re.fullmatch(r"[a-f0-9]{64}",item[key]) is not None)
    require(re.fullmatch(P.STORE,item["generation"]) is not None and "-nixos-system-" in item["generation"])
    require(re.fullmatch(P.STORE,item["configuration"]) is not None and item["configuration"].endswith("-nginx.conf"))
    require(re.fullmatch(P.STORE+r"/bin/nginx",item["executable"]) is not None)
    require(re.fullmatch(P.STORE+r"/nginx.service",item["unit"]) is not None)
    return item


def command(item,args,timeout=30,capture=False):
    result=subprocess.run(args,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL,timeout=timeout,check=False,env={"LANG":"C","LC_ALL":"C"})
    require(result.returncode==0)
    if capture:
        require(len(result.stdout)<=16384)
        return result.stdout


def manager(item,*args,capture=False):
    return command(item,[item["generation"]+"/sw/bin/systemctl",*args],timeout=60,capture=capture)


def current(item,temporary):
    require(os.path.realpath("/run/current-system")==item["generation"])
    raw=manager(item,"show","nginx.service","--no-pager",
                "--property=LoadState,ActiveState,ExecStart,FragmentPath,DropInPaths",capture=True)
    values=dict(line.split("=",1) for line in raw.decode("ascii").splitlines())
    require(values["LoadState"]=="loaded" and values["ActiveState"]=="active")
    require(os.path.realpath(values["FragmentPath"])==item["unit"])
    paths=re.findall(r"(?:^|[ {;])path=([^ ;}]+)",values["ExecStart"])
    args=re.findall(r"(?:^|[ ;])argv\[\]=([^;{}]+)",values["ExecStart"])
    expected=str(TEMPORARY) if temporary else item["configuration"]
    require(paths==[item["executable"]] and len(args)==1 and args[0].strip().split()==[item["executable"],"-c",expected])
    require(values["DropInPaths"]==(str(DROPIN) if temporary else ""))


def sealed_configuration(item):
    old=P.immutable(item["configuration"],1024*1024)
    require(digest(old)==item["configuration_sha256"])
    require(digest(P.immutable(item["executable"],128*1024*1024,True))==item["executable_sha256"])
    require(digest(P.immutable(item["unit"],65536))==item["unit_sha256"])
    begin,end=P.server_position(old)
    require(digest(old[begin:end+1])==item["tls_server_sha256"])
    return old[:end]+LOCATION+old[end:]


def protected(path,create=False):
    fd=os.open("/",os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        for part in path.parts[1:]:
            if create:
                try:os.mkdir(part,0o700,dir_fd=fd)
                except FileExistsError:pass
            next_fd=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=fd)
            os.close(fd);fd=next_fd
            meta=os.fstat(fd)
            require(meta.st_uid==0 and not stat.S_IMODE(meta.st_mode)&0o022)
        return fd
    except BaseException:
        os.close(fd);raise


def regular(directory,name,maximum,mode,gid):
    fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=directory)
    with os.fdopen(fd,"rb") as source:
        meta=os.fstat(source.fileno())
        require(stat.S_ISREG(meta.st_mode) and meta.st_uid==0 and meta.st_gid==gid and meta.st_nlink==1
                and stat.S_IMODE(meta.st_mode)==mode and meta.st_size<=maximum)
        raw=source.read(maximum+1)
    require(len(raw)==meta.st_size)
    return raw


def create(directory,name,raw,mode=0o600,gid=0):
    fd=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,mode,dir_fd=directory)
    with os.fdopen(fd,"wb") as output:
        os.fchown(output.fileno(),0,gid)
        os.fchmod(output.fileno(),mode)
        output.write(raw);output.flush();os.fsync(output.fileno())
    os.fsync(directory)


def state(item,prepared):return encode({"binding":item,"temporary_sha256":digest(prepared),"armed":True})


def override(item):
    return ("[Service]\nExecStart=\nExecStart="+item["executable"]+" -c "+str(TEMPORARY)+"\n").encode()


def portal_socket():
    parent=protected(SOCKET.parent)
    try:
        directory=os.fstat(parent);meta=os.stat(SOCKET.name,dir_fd=parent,follow_symlinks=False)
        require(directory.st_uid==0 and directory.st_gid==60 and stat.S_IMODE(directory.st_mode)==0o750)
        require(stat.S_ISSOCK(meta.st_mode) and meta.st_uid==0 and meta.st_gid==60 and stat.S_IMODE(meta.st_mode)==0o660)
    finally:os.close(parent)


def rollback(item,work):
    try:raw=regular(work,"state.json",16384,0o600,0)
    except FileNotFoundError:return False
    prepared=sealed_configuration(item)
    require(raw==state(item,prepared))
    require(regular(work,"nginx.conf",1024*1024+8192,0o640,60)==prepared)
    runtime=protected(DROPIN.parent)
    try:
        try:existing=regular(runtime,DROPIN.name,4096,0o600,0)
        except FileNotFoundError:existing=None
        require(existing is None or existing==override(item))
        if existing is not None:
            os.unlink(DROPIN.name,dir_fd=runtime);os.fsync(runtime)
    finally:os.close(runtime)
    # The runtime override is removed even if an administrator has switched
    # generation. Never restart a different generation using this old binding.
    manager(item,"daemon-reload")
    require(os.path.realpath("/run/current-system")==item["generation"])
    # A failed temporary start must not leave restoration blocked by the old
    # unit's start-rate counter. This changes only that fixed unit's state.
    manager(item,"reset-failed","nginx.service")
    manager(item,"restart","nginx.service")
    current(item,False)
    for name in ("ready.json","state.json","nginx.conf"):
        try:os.unlink(name,dir_fd=work)
        except FileNotFoundError:pass
    os.fsync(work)
    return True


def apply(item,work):
    current(item,False)
    prepared=sealed_configuration(item)
    portal_socket()
    runtime=protected(DROPIN.parent,True)
    try:
        require(not os.listdir(runtime))
        create(work,"nginx.conf",prepared,0o640,60)
        try:
            command(item,[item["executable"],"-t","-c",str(TEMPORARY)],timeout=20)
        except BaseException:
            os.unlink("nginx.conf",dir_fd=work);raise
        create(work,"state.json",state(item,prepared))
        try:
            create(runtime,DROPIN.name,override(item))
            manager(item,"daemon-reload")
            manager(item,"restart","nginx.service")
            current(item,True)
            opened=time.monotonic()
            create(work,"ready.json",encode({"code":"PASSKEY_ROUTE_OPEN","origin":"https://log.mrj.am",
                                             "prefix":P.PREFIX,"expires_after_seconds":TTL}))
            print('{"schema_version":1,"code":"PASSKEY_ROUTE_OPEN"}',flush=True)
            while time.monotonic()-opened<TTL:
                portal_socket()
                time.sleep(1)
        finally:
            rollback(item,work)
    finally:os.close(runtime)


def main():
    try:
        require(os.geteuid()==0 and len(sys.argv)==2 and sys.argv[1] in ("apply","rollback"))
        os.umask(0o077)
        item=binding()
        work=protected(WORK,True)
        try:
            fcntl.flock(work,fcntl.LOCK_EX|fcntl.LOCK_NB)
            # This directory holds only generated public code and closed status.
            os.fchown(work,0,60);os.fchmod(work,0o750)
            signal.signal(signal.SIGTERM,lambda *_: (_ for _ in ()).throw(Stopped()))
            signal.signal(signal.SIGINT,lambda *_: (_ for _ in ()).throw(Stopped()))
            if sys.argv[1]=="apply":apply(item,work)
            else:rollback(item,work)
        finally:os.close(work)
    except Stopped:
        print('{"schema_version":1,"code":"PASSKEY_ROUTE_CLOSED"}')
        return 0
    except BaseException:
        print('{"schema_version":1,"code":"PASSKEY_ROUTE_REFUSED"}')
        return 1
    print('{"schema_version":1,"code":"PASSKEY_ROUTE_CLOSED"}')
    return 0


if __name__=="__main__":raise SystemExit(main())
