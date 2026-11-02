#!/usr/bin/env python3
"""Closed validation of public HTTP-level MIME/CGI includes; no private includes."""
import hashlib,json,os,re,stat,sys
PREVIOUS="/nix/store/jn9rf2fgk2y6dbhdnjwkmfww3pchkyb9-nixos-system-nixos-26.05.8639.c5c4a43b0e80"
CONFIG="/nix/store/g0v9ji72630xhgg5q3alz0883m7pjbkb-nginx.conf"
SHA256="8e540ab2d53da5b03132176e5947eb40cc17866e1dba939725b77901b8155857"
STORE=r"/nix/store/[0-9a-df-np-sv-z]{32}-[A-Za-z0-9+._?=-]+"
NGINX="/nix/store/hrsgwp6dqnr9y9svhjzvxw0phgmqvnqk-nginx-1.30.4"
PUBLIC_CGI={
 NGINX+'/conf/fastcgi.conf':('fastcgi_param','b2c3d480a58f61f3a7dc61850b461e892e36f236317765a4f2f6d558c928fa57'),
 NGINX+'/conf/uwsgi_params':('uwsgi_param','015cb581c2eb84b1a1ac9b575521d5881f791f632bfa62f34b26ba97d70c0d4f'),
}

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

def tree(raw):
    stream=tokens(raw);index=0
    def block(nested,depth):
        nonlocal index
        require(depth<=20)
        nodes=[];words=[]
        while index<len(stream):
            value,_,_=stream[index];index+=1
            if value=='}':
                require(nested and not words);return nodes
            if value in ('{',';'):
                require(words)
                nodes.append((words,block(True,depth+1) if value=='{' else None));words=[]
            else:words.append(value)
        require(not nested and not words);return nodes
    return block(False,0)


def mime_path(path):
    return bool(re.fullmatch(STORE+r'/etc/nginx/mime.types',path) or
                (re.fullmatch(STORE,path) and path.endswith('-mime.types')))


def mime_only(raw):
    nodes=tree(raw)
    require(len(nodes)==1 and nodes[0][0]==['types'] and nodes[0][1] is not None)
    entries=nodes[0][1]
    require(0<len(entries)<=10000)
    for words,children in entries:
        # The packaged MIME registry also lists two types with no extensions.
        require(children is None and len(words)>=1)
        require(re.fullmatch(r'[A-Za-z0-9!#$&^_.+-]+/[A-Za-z0-9!#$&^_.+-]+',words[0]) is not None)
        # Extensions are data, including the registry's UTF-8 geocube suffix.
        require(all(re.fullmatch(r'[A-Za-z0-9_.+\x80-\xff-]+',word) is not None for word in words[1:]))
    return len(entries)


def classify(words,children,reader=immutable):
    if children is not None or len(words)!=2:
        return {'state':'unclassified-not-read'}
    path=words[1]
    if path in PUBLIC_CGI:
        directive,expected=PUBLIC_CGI[path]
        raw=reader(path,65536)
        require(hashlib.sha256(raw).hexdigest()==expected)
        nodes=tree(raw)
        require(nodes and all(child is None and word[0]==directive and len(word) in (3,4)
                             for word,child in nodes))
        return {'state':'verified-public-non-csp-code','kind':directive,'path':path,'sha256':expected,
                'directive_count':len(nodes),'contains_csp_directives':False}
    if mime_path(path):
        raw=reader(path,1024*1024)
        count=mime_only(raw)
        return {'state':'verified-public-non-csp-code','kind':'mime-types','path':path,
                'sha256':hashlib.sha256(raw).hexdigest(),'directive_count':count,'contains_csp_directives':False}
    value={'state':'unclassified-not-read'}
    if re.fullmatch(STORE+r'(?:/[A-Za-z0-9+._=-]+)*',path):value['immutable_include_path']=path
    return value


def observe():
    require(os.geteuid()==0 and os.path.realpath('/run/current-system')==PREVIOUS)
    raw=immutable(CONFIG,1024*1024)
    require(hashlib.sha256(raw).hexdigest()==SHA256)
    http=[children for words,children in tree(raw) if words==['http']]
    require(len(http)==1 and http[0] is not None)
    includes=[classify(words,children) for words,children in http[0] if words[0]=='include']
    require(len(includes)<=32)
    return {'schema_version':1,'code':'PASSKEY_HTTP_INCLUDE_CODE_OBSERVED','configuration_sha256':SHA256,
            'http_includes':includes,'all_http_includes_public_non_csp_code':all(value['state']=='verified-public-non-csp-code' for value in includes),
            'private_includes_followed':False,'production_mutation':False}


def main():
    if len(sys.argv)!=1:return 64
    try:value=observe()
    except Exception:
        print('{"schema_version":1,"code":"PASSKEY_HTTP_INCLUDE_OBSERVATION_REFUSED"}');return 1
    print(json.dumps(value,sort_keys=True,separators=(',',':')));return 0


if __name__=='__main__':raise SystemExit(main())
