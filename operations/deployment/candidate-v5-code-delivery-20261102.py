"""Sealed delivery of the qualified human-login tool; no application activation.

This source is a template with no operational defaults. Its final delivery
copy embeds an exact reviewed export digest, size, store paths and unit hash.
The entrypoint accepts only that byte stream on stdin and no arguments.
"""
import hashlib
import fcntl
import json
import os
from pathlib import Path
import re
import resource
import signal
import stat
import subprocess
import sys

RELEASE = {'schema_version': 1, 'export_sha256': 'f2171435d0a2bb84d5c18c15c89cbe8c7e0ce5e87071726559ca48cca2eba1cb', 'export_bytes': 14376800, 'required_free_bytes': 1106923360, 'store_paths': ['/nix/store/124ll4pddj14whprlwn21ihkm9q8vq82-unit-script-mrjam-bootstrap-journal-start', '/nix/store/1i46491bsxkwy84sk8ycmvpphchr9ajg-system-units', '/nix/store/3xpjjmxgxby0vs0dnnyrf7vwqpcp18sr-unit-mrjam-rust-blue.service', '/nix/store/5yqv8fsy6qhw45qs53qnirib9vl3cjhq-mrjam-kanidm-worker-provision-2', '/nix/store/9hi42i79xwv298xh21ih1azz5xbb8hmm-unit-mrjam-rust-blue.service', '/nix/store/9izcvd8wawanhpxhih1cvmqgg5bdsl9z-etc', '/nix/store/asl1zrmynbw16n9bcn1sp7q4m841s1j8-unit-mrjam-rust-green.service', '/nix/store/dc09bjfaf8wsfrwxpkqw0bi3xhp3nklm-nixos-system-srv1982677-26.05pre-git', '/nix/store/dcnw9gr779pn7jhsyf7wqriz97g45x9w-system-units', '/nix/store/hbfh9zzrv35kxck3p56yv7pxxw22fb3y-nixos-system-srv1982677-26.05pre-git', '/nix/store/j7hxh8lciy43px1zapj6sbq6fw2lzxb5-etc', '/nix/store/nn4sx38x6snsq4jm4hv13j2w8nrki5jk-mrjam-audition-schema-adoption-2', '/nix/store/ph06qf893mn2g608mnsgzpvc19cdxdn4-unit-mrjam-bootstrap-journal.service', '/nix/store/w25djyzhrrbkc46fvzb7zjcbp1c2j549-unit-mrjam-kanidm-worker-provision.service', '/nix/store/wasrcrd9a76d1gpzzrhs0qkxbdqzwdrw-mrjam-server-mateval-typed-readiness-1', '/nix/store/y3vx7wl0419wqzkfdwckf2kdmk6sdfv5-mrjam-runtime-blue', '/nix/store/zzfz80j1qwxwsv358lf57pppagglhmkk-mrjam-runtime-green'], 'package': '/nix/store/5yqv8fsy6qhw45qs53qnirib9vl3cjhq-mrjam-kanidm-worker-provision-2', 'unit_store': '/nix/store/w25djyzhrrbkc46fvzb7zjcbp1c2j549-unit-mrjam-kanidm-worker-provision.service', 'unit_sha256': '19dd8383236b62acfb0aa7fb081b00e78c42314b7418f94b5aa50ee9e82896cc'}
PREVIOUS = "/nix/store/jn9rf2fgk2y6dbhdnjwkmfww3pchkyb9-nixos-system-nixos-26.05.8639.c5c4a43b0e80"
DIRECTORY = Path("/var/lib/mrjam-deployment-delivery/candidate-v5-code-20261102")
UNIT = "mrjam-kanidm-worker-provision.service"
SYSTEMD = Path("/run/systemd/system")
STORE = re.compile(r"/nix/store/[0-9a-df-np-sv-z]{32}-[A-Za-z0-9+._?=-]+\Z")


class Refused(RuntimeError):
    pass


def require(value):
    if not value:
        raise Refused("PROVISION_DELIVERY_REFUSED")


def validate_release(value):
    require(isinstance(value,dict) and set(value)=={
        "schema_version","export_sha256","export_bytes","required_free_bytes","store_paths","package","unit_store","unit_sha256"})
    require(type(value["schema_version"]) is int and value["schema_version"]==1)
    for field in ("export_sha256","unit_sha256"):
        require(isinstance(value[field],str) and re.fullmatch(r"[a-f0-9]{64}",value[field]))
    require(type(value["export_bytes"]) is int and 0<value["export_bytes"]<8*1024**3)
    require(type(value["required_free_bytes"]) is int
            and 2*value["export_bytes"]+1024**3<=value["required_free_bytes"]<=64*1024**3)
    paths=value["store_paths"]
    require(isinstance(paths,list) and 0<len(paths)<10000 and len(set(paths))==len(paths))
    require(all(isinstance(path,str) and STORE.fullmatch(path) for path in paths))
    require(value["package"] in paths and value["unit_store"] in paths)
    require(value["package"].endswith("-mrjam-kanidm-worker-provision-2"))
    return value


def protected_directory(path, create=False):
    """No symlink traversal and no writable ancestor outside root."""
    descriptor=os.open("/",os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        for part in Path(path).parts[1:]:
            if create:
                try:
                    os.mkdir(part,0o700,dir_fd=descriptor)
                    os.fsync(descriptor)
                except FileExistsError:
                    pass
            child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=descriptor)
            os.close(descriptor);descriptor=child
            item=os.fstat(descriptor)
            require(item.st_uid==0 and not stat.S_IMODE(item.st_mode)&0o022)
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def receive(stream, directory, release):
    # Only this code archive is overwritten on an interrupted transfer. The
    # directory binding is checked before this function, never inferred from
    # an existing arbitrary file. No secret or application data lives here.
    fd=os.open("export.partial",os.O_WRONLY|os.O_CREAT|os.O_NOFOLLOW|os.O_CLOEXEC,0o600,dir_fd=directory)
    try:
        item=os.fstat(fd)
        require(stat.S_ISREG(item.st_mode) and item.st_uid==os.geteuid() and item.st_nlink==1
                and stat.S_IMODE(item.st_mode)==0o600)
        os.ftruncate(fd,0)
        digest=hashlib.sha256();total=0
        with os.fdopen(fd,"wb",closefd=False) as output:
            while total<=release["export_bytes"]:
                block=stream.read(min(1024*1024,release["export_bytes"]-total+1))
                if not block:
                    break
                total+=len(block)
                require(total<=release["export_bytes"])
                digest.update(block);output.write(block)
            require(total==release["export_bytes"] and digest.hexdigest()==release["export_sha256"])
            output.flush();os.fsync(fd)
        # An existing identical complete archive is safe to replace with these
        # just-verified identical code bytes; no unverified bytes get imported.
        os.rename("export.partial","export.nar",src_dir_fd=directory,dst_dir_fd=directory)
        os.fsync(directory)
    finally:
        os.close(fd)


def command(args, *, source=None, capture=False):
    result=subprocess.run(args,stdin=source if source is not None else subprocess.DEVNULL,
                          stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL,check=False,timeout=300,
                          env={"LANG":"C","LC_ALL":"C","NIX_PATH":""})
    require(result.returncode==0)
    if capture:
        require(len(result.stdout)<=2*1024*1024)
        return result.stdout


def install_unit(directory, unit_path):
    try:
        existing=os.readlink(UNIT,dir_fd=directory)
    except FileNotFoundError:
        os.symlink(str(unit_path),UNIT,dir_fd=directory)
        os.fsync(directory)
    else:
        require(existing==str(unit_path))


def deliver(release, stream):
    release=validate_release(release)
    require(os.geteuid()==0 and os.path.realpath("/run/current-system")==PREVIOUS)
    work=protected_directory(DIRECTORY,create=True)
    try:
        # Held through receive, import, unit installation and manager reload.
        # A concurrent stream must never mutate the inode just verified here.
        fcntl.flock(work,fcntl.LOCK_EX|fcntl.LOCK_NB)
        require(stat.S_IMODE(os.fstat(work).st_mode)==0o700)
        for filesystem in (os.fstatvfs(work),os.statvfs('/nix/store')):
            require(filesystem.f_bavail*filesystem.f_frsize>=release['required_free_bytes'])
        # This public binding makes a resumed transfer unable to switch the
        # allowed payload or install another unit in the same delivery slot.
        binding=(json.dumps(release,sort_keys=True,separators=(",",":"))+"\n").encode()
        try:
            fd=os.open("release.json",os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=work)
        except FileExistsError:
            fd=os.open("release.json",os.O_RDONLY|os.O_NOFOLLOW,dir_fd=work)
            with os.fdopen(fd,"rb") as existing:
                meta=os.fstat(existing.fileno())
                require(stat.S_ISREG(meta.st_mode) and meta.st_uid==0 and meta.st_nlink==1 and stat.S_IMODE(meta.st_mode)==0o600)
                require(existing.read(len(binding)+1)==binding)
        else:
            with os.fdopen(fd,"wb") as output:
                output.write(binding);output.flush();os.fsync(output.fileno())
            os.fsync(work)
        receive(stream,work,release)
        fd=os.open("export.nar",os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=work)
        with os.fdopen(fd,"rb") as archive:
            imported=command([PREVIOUS+"/sw/bin/nix-store","--import"],source=archive,capture=True)
        observed=imported.decode("ascii").splitlines()
        require(len(observed)==len(set(observed)) and set(observed)==set(release["store_paths"]))
        command([PREVIOUS+"/sw/bin/nix-store","--verify-path",*release["store_paths"]])
        path=Path(release["unit_store"])/UNIT
        # This is public, immutable generated unit code, never private config.
        require(hashlib.sha256(path.read_bytes()).hexdigest()==release["unit_sha256"])
        runtime=protected_directory(SYSTEMD)
        try:
            install_unit(runtime,path)
        finally:
            os.close(runtime)
        command([PREVIOUS+"/sw/bin/systemctl","daemon-reload"])
    finally:
        os.close(work)
    return {"schema_version":1,"code":"HUMAN_LOGIN_TOOL_INSTALLED",
            "application_activation":False,"credential_creation":False}


def main():
    try:
        require(len(sys.argv)==1)
        resource.setrlimit(resource.RLIMIT_CORE,(0,0))
        os.umask(0o077)
        signal.signal(signal.SIGALRM,lambda *_: (_ for _ in ()).throw(Refused()))
        signal.alarm(900)
        value=deliver(RELEASE,sys.stdin.buffer)
    except Exception:
        print('{"schema_version":1,"code":"PROVISION_DELIVERY_REFUSED"}')
        return 1
    print(json.dumps(value,sort_keys=True,separators=(",",":")))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
