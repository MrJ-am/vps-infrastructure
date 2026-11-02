#!/usr/bin/env python3
"""Closed immutable Nginx code metadata for one temporary HTTPS route."""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

PREVIOUS = "/nix/store/jn9rf2fgk2y6dbhdnjwkmfww3pchkyb9-nixos-system-nixos-26.05.8639.c5c4a43b0e80"
CONFIG = "/nix/store/g0v9ji72630xhgg5q3alz0883m7pjbkb-nginx.conf"
PREFIX = "/_mrjam-worker-provision/"
STORE = r"/nix/store/[0-9a-df-np-sv-z]{32}-[A-Za-z0-9+._?=-]+"


def require(value):
    if not value:
        raise ValueError("PASSKEY_NGINX_OBSERVATION_REFUSED")


def immutable(path, maximum, executable=False):
    require(re.fullmatch(STORE+r"(?:/[A-Za-z0-9+._=-]+)*",path) is not None)
    require(os.path.realpath(path)==path)
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    with os.fdopen(fd,"rb") as source:
        meta=os.fstat(source.fileno())
        require(stat.S_ISREG(meta.st_mode) and meta.st_uid==0 and not stat.S_IMODE(meta.st_mode)&0o222)
        require(0<meta.st_size<=maximum and (not executable or stat.S_IMODE(meta.st_mode)&0o111))
        raw=source.read(maximum+1)
    require(len(raw)==meta.st_size)
    if executable:
        require(raw.startswith(b"\x7fELF"))
    return raw


def tokens(raw):
    """Small fail-closed Nginx tokenizer retaining byte insertion positions."""
    require(isinstance(raw,bytes) and len(raw)<=1024*1024 and b"\0" not in raw)
    # Latin-1 keeps a one-to-one mapping to byte offsets, including comments.
    text=raw.decode("latin1")
    out=[];word=[];start=None;quote=None;i=0
    while i<len(text):
        char=text[i]
        if char=="\\":
            require(i+1<len(text));start=i if start is None else start
            i+=1;word.append(text[i])
        elif quote:
            if char==quote:quote=None
            else:word.append(char)
        elif char in "\"'":
            start=i if start is None else start;quote=char
        elif char=="#":
            if start is not None:out.append(("".join(word),start,i));word=[];start=None
            end=text.find("\n",i);i=len(text) if end<0 else end
            continue
        elif char.isspace() or char in "{};":
            if start is not None:out.append(("".join(word),start,i));word=[];start=None
            if char in "{};":out.append((char,i,i+1))
        else:
            start=i if start is None else start;word.append(char)
        require(len(word)<=16384 and len(out)<=100000)
        i+=1
    require(quote is None and start is None)
    return out


def server_position(raw):
    require(PREFIX.encode() not in raw)
    stream=tokens(raw);index=0
    def block(depth,nested):
        nonlocal index
        require(depth<=20)
        nodes=[];words=[];begin=None
        while index<len(stream):
            token,start,end=stream[index];index+=1
            if token=="}":
                require(nested and not words)
                return nodes,start
            if token in ("{",";"):
                require(words)
                children,closing=block(depth+1,True) if token=="{" else (None,None)
                nodes.append((words,children,begin,closing))
                words=[];begin=None
            else:
                if begin is None:begin=start
                words.append(token)
        require(not nested and not words)
        return nodes,None
    tree,_=block(0,False)
    http=[children for words,children,_,_ in tree if words==["http"] and children is not None]
    require(len(http)==1)
    matches=[]
    for words,children,begin,closing in http[0]:
        if words!=["server"] or children is None:continue
        names=[words[1:] for words,child,_,_ in children if words[0]=="server_name" and child is None]
        if not any("log.mrj.am" in group for group in names):continue
        require(names==[["log.mrj.am"]])
        listeners=[words[1:] for words,child,_,_ in children if words[0]=="listen" and child is None]
        secure=[words for words in listeners if "ssl" in words]
        if not secure:continue
        require(len(secure)==len(listeners) and all(words[0]=="443" or words[0].endswith(":443") for words in secure))
        require(not any(words[0]=="include" for words,_,_,_ in children))
        matches.append((begin,closing))
    require(len(matches)==1)
    return matches[0]


def parse_exec(raw):
    paths=re.findall(r"(?:^|[ {;])path=([^ ;}]+)",raw)
    args=re.findall(r"(?:^|[ ;])argv\[\]=([^;{}]+)",raw)
    require(len(paths)==len(args)==1)
    binary=paths[0]
    require(re.fullmatch(STORE+r"/bin/nginx",binary) is not None)
    require(args[0].strip().split()==[binary,"-c",CONFIG])
    return binary


def observe():
    require(os.geteuid()==0 and os.path.realpath("/run/current-system")==PREVIOUS)
    result=subprocess.run([PREVIOUS+"/sw/bin/systemctl","show","nginx.service","--no-pager",
                           "--property=LoadState,ActiveState,ExecStart,FragmentPath,DropInPaths"],
                          stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                          timeout=15,check=False,env={"LANG":"C","LC_ALL":"C"})
    require(result.returncode==0 and len(result.stdout)<=16384)
    values=dict(line.split("=",1) for line in result.stdout.decode("ascii").splitlines())
    require(set(values)=={"LoadState","ActiveState","ExecStart","FragmentPath","DropInPaths"})
    require(values["LoadState"]=="loaded" and values["ActiveState"]=="active" and values["DropInPaths"]=="")
    binary=parse_exec(values["ExecStart"])
    require(values["FragmentPath"] in ("/etc/systemd/system/nginx.service",PREVIOUS+"/etc/systemd/system/nginx.service"))
    unit=os.path.realpath(values["FragmentPath"])
    config=immutable(CONFIG,1024*1024)
    begin,end=server_position(config)
    return {"schema_version":1,"code":"PASSKEY_NGINX_CODE_OBSERVED",
            "generation":PREVIOUS,"configuration":CONFIG,"configuration_sha256":hashlib.sha256(config).hexdigest(),
            "executable":binary,"executable_sha256":hashlib.sha256(immutable(binary,128*1024*1024,True)).hexdigest(),
            "unit":unit,"unit_sha256":hashlib.sha256(immutable(unit,65536)).hexdigest(),
            "tls_server_sha256":hashlib.sha256(config[begin:end+1]).hexdigest(),
            "origin":"https://log.mrj.am","rp_id":"log.mrj.am","temporary_prefix":PREFIX,
            "unique_tls_server":True,"runtime_overrides_absent":True,
            "private_configuration_read":False,"logs_read":False,"production_mutation":False}


def main():
    if len(sys.argv)!=1:return 64
    try:value=observe()
    except Exception:
        print('{"schema_version":1,"code":"PASSKEY_NGINX_OBSERVATION_REFUSED"}')
        return 1
    print(json.dumps(value,sort_keys=True,separators=(",",":")))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
