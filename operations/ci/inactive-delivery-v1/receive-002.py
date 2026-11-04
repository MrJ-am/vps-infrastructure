"""Sealed code import after release005; no unit, profile or service mutation."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import selectors
import signal
import stat
import subprocess
import sys
import time

RELEASE = {'schema_version': 1, 'export_sha256': '5e14647a408a9d18951d394d9af86d9dc1d7512c5c52ffed4b2b0eae5c6f754d', 'export_bytes': 838802424, 'required_free_bytes': 2751346672, 'artifacts': {'/nix/store/2va2x1g4ncjhaih1dk0zxvi97s832pw9-mrjam-rust-toolchain-1.99.1': {'nar_hash': 'sha256-mmCy2cUsZ9UM7MvxijRyLi3odAz5qCck1zvdvmEjar4=', 'references': ['/nix/store/2va2x1g4ncjhaih1dk0zxvi97s832pw9-mrjam-rust-toolchain-1.99.1', '/nix/store/7b063z98zcilpmzj2sz7sl56gl84zf02-zlib-1.3.2', '/nix/store/dphsh3jff8w6n9p3xbfmkia5krqwv52f-glibc-2.42-103', '/nix/store/hc49zakwkkyp9zlyl80b71jhxkpn4hsx-bash-5.3p9', '/nix/store/wkkvmvz3vnbfl3rkf85gp5p5mgp34ak3-gcc-15.3.0-libgcc']}, '/nix/store/h4pqd20idzp9vn5hywrq9kfzmjdzgjsr-mrjam-node-build-tool-24.19.0': {'nar_hash': 'sha256-kVJ2A6L/WSW5pGoGrimu8mlK5AE9eqjj8Jre/gC7zjE=', 'references': ['/nix/store/0ba5kj6r0zhfwd84l5vzccqvx7amlq2c-gcc-15.3.0-lib', '/nix/store/dphsh3jff8w6n9p3xbfmkia5krqwv52f-glibc-2.42-103', '/nix/store/wkkvmvz3vnbfl3rkf85gp5p5mgp34ak3-gcc-15.3.0-libgcc']}, '/nix/store/cdilc0zq2gxyjpgcynnwrgr6hxfv5r38-mrjam-elm-validation-tools': {'nar_hash': 'sha256-QTRbqWd55ur02m1HSV3gTCpnDEvH0ZE23VCA/AXKMx4=', 'references': ['/nix/store/cdilc0zq2gxyjpgcynnwrgr6hxfv5r38-mrjam-elm-validation-tools', '/nix/store/h4pqd20idzp9vn5hywrq9kfzmjdzgjsr-mrjam-node-build-tool-24.19.0', '/nix/store/hc49zakwkkyp9zlyl80b71jhxkpn4hsx-bash-5.3p9']}, '/nix/store/chk7gc2ii1xmw6srhdh0fq7cjxfpy391-mrjam-current-validator-proposed-policy-v2.json': {'nar_hash': 'sha256-pT3VQX3kowQTMkpxps6LWKqm1qzXK9WEJRwb1mr2xAE=', 'references': []}, '/nix/store/xjfr4p44v9hsw80dss844pn1szcaw2ha-libcap-2.77-lib': {'nar_hash': 'sha256-mZnt/UIOfhGLktB+IZMYVuQECWbr6TQTIa8LlwVjFko=', 'references': ['/nix/store/dphsh3jff8w6n9p3xbfmkia5krqwv52f-glibc-2.42-103']}, '/nix/store/f2bsh1n6snqdldnjdshdy1lw3hnlfxwi-bubblewrap-0.12.0': {'nar_hash': 'sha256-oEg6ohBOoUDWHmCjWTTqdACfvQVZbmkIhA75z1hcE5M=', 'references': ['/nix/store/6qr55y5rlrdvm3qy9fpa2pks7xa50yl3-libselinux-3.10', '/nix/store/dphsh3jff8w6n9p3xbfmkia5krqwv52f-glibc-2.42-103', '/nix/store/xjfr4p44v9hsw80dss844pn1szcaw2ha-libcap-2.77-lib']}, '/nix/store/ifpnqj76y16xh8rzxprl0linflgamhdp-mrjam-pinned-browser-resources': {'nar_hash': 'sha256-F2LHwsZ9ab6HtmuguwHkubZEaJFguRafKPfbAft2FYI=', 'references': []}, '/nix/store/9ldbnd0p3q858l2yznakj63hz3rj10p0-expand-response-params': {'nar_hash': 'sha256-Nfj1NuCMUTo7r77jpR4p+PepOLlSCkw2SQDqNR+NvPU=', 'references': ['/nix/store/dphsh3jff8w6n9p3xbfmkia5krqwv52f-glibc-2.42-103']}, '/nix/store/n56d9xz7m3sc1gvyr2hi9v082abq5sdb-pkg-config-0.29.2': {'nar_hash': 'sha256-i1l+jUIqX8XR6cisXMaTZG62mZQNx2Y7TB0e7WRfC0g=', 'references': ['/nix/store/dphsh3jff8w6n9p3xbfmkia5krqwv52f-glibc-2.42-103', '/nix/store/n56d9xz7m3sc1gvyr2hi9v082abq5sdb-pkg-config-0.29.2']}, '/nix/store/pilsssjjdxvdphlg2h19p0bfx5q0jzkn-strip.sh': {'nar_hash': 'sha256-/kocrQCaIGEh7zh26MuHLTtmIp5yJylHriY/yVFhPk4=', 'references': []}, '/nix/store/ilc04wmg2xh5jncdbc4v5zc0jdzag4mz-pkg-config-wrapper-0.29.2': {'nar_hash': 'sha256-Z741zJi2J0pVawrAsQMuIbb9GLvw87dV4FjTJl7PytM=', 'references': ['/nix/store/9ldbnd0p3q858l2yznakj63hz3rj10p0-expand-response-params', '/nix/store/hc49zakwkkyp9zlyl80b71jhxkpn4hsx-bash-5.3p9', '/nix/store/ilc04wmg2xh5jncdbc4v5zc0jdzag4mz-pkg-config-wrapper-0.29.2', '/nix/store/n56d9xz7m3sc1gvyr2hi9v082abq5sdb-pkg-config-0.29.2', '/nix/store/pilsssjjdxvdphlg2h19p0bfx5q0jzkn-strip.sh']}, '/nix/store/kdnbkivxcszycbn8fqm0hi1d77gfqlnc-mrjam-protected-http-contract': {'nar_hash': 'sha256-dmZMVdGg1PcXi7vZwsMsn2oxIa+MdDSLCUXexs0Zqvo=', 'references': []}, '/nix/store/l6c4bjcvy4r6yyh2fyj4y7347dxzv6vg-overrides': {'nar_hash': 'sha256-flzxL48kxUFDmaez/sSlGjqOY+iR5wwilKR+t1Lv/Cc=', 'references': []}, '/nix/store/q0kvfykalwya20s1ab635ldwbk1r0336-mrjam-verifier-support': {'nar_hash': 'sha256-PgM0St3ltTkhEWn1jmPniVRvJgwY55bk1UZFtzRwnvQ=', 'references': []}, '/nix/store/v8izrc2pmwnmfm4ariisf2jh0gf5wpvi-mrjam-canonical-review-rules': {'nar_hash': 'sha256-Zc9MxWq7fova1JaVS1T/mv6UqeiRyiJdvl8qfP9ikKc=', 'references': []}, '/nix/store/mjxf7qs56s2qyaa309m5634xg73142yc-simdutf-9.0.0': {'nar_hash': 'sha256-zwmosC/4VMUpIM/vDrxqj6Lv6bcwf9p3SFWGI510Wio=', 'references': ['/nix/store/0ba5kj6r0zhfwd84l5vzccqvx7amlq2c-gcc-15.3.0-lib', '/nix/store/dphsh3jff8w6n9p3xbfmkia5krqwv52f-glibc-2.42-103', '/nix/store/mjxf7qs56s2qyaa309m5634xg73142yc-simdutf-9.0.0']}, '/nix/store/124ca9b7djjkzidqdqzd93mcwqvbpidg-ada-3.4.4': {'nar_hash': 'sha256-I9i3Inrik0xrTaRx4Jyp09LM2/umvSHoroA4CY6es4I=', 'references': ['/nix/store/0ba5kj6r0zhfwd84l5vzccqvx7amlq2c-gcc-15.3.0-lib', '/nix/store/124ca9b7djjkzidqdqzd93mcwqvbpidg-ada-3.4.4', '/nix/store/dphsh3jff8w6n9p3xbfmkia5krqwv52f-glibc-2.42-103', '/nix/store/mjxf7qs56s2qyaa309m5634xg73142yc-simdutf-9.0.0']}, '/nix/store/5lqvbgf40v78y7i5d1kcyzz23jky5yqp-simdutf-6.5.0': {'nar_hash': 'sha256-vdrdgNqQdhsH+PtwSjvwBSOF4h1CtiWjG2YRHiCIDDM=', 'references': ['/nix/store/0ba5kj6r0zhfwd84l5vzccqvx7amlq2c-gcc-15.3.0-lib', '/nix/store/5lqvbgf40v78y7i5d1kcyzz23jky5yqp-simdutf-6.5.0', '/nix/store/dphsh3jff8w6n9p3xbfmkia5krqwv52f-glibc-2.42-103']}, '/nix/store/87ygcks0lay6r3bxn8sn6m6lpwxz3ywk-ngtcp2-1.22.1-dev': {'nar_hash': 'sha256-mLr48/f68uLuNUqL8zeCY6LaxTMY7pCxgpbRDeI99fw=', 'references': ['/nix/store/41xwpwwpg8jxqgar1jf9lww0xkfy9mjc-ngtcp2-1.22.1', '/nix/store/87ygcks0lay6r3bxn8sn6m6lpwxz3ywk-ngtcp2-1.22.1-dev']}, '/nix/store/a3al4xgkxqp4w718d5ai4nhrk4blm6am-simdjson-4.6.4': {'nar_hash': 'sha256-6C67XDQUH3SYtLU/4LmwB4wMAUfe+e3JgVmnbhxoguI=', 'references': ['/nix/store/0ba5kj6r0zhfwd84l5vzccqvx7amlq2c-gcc-15.3.0-lib', '/nix/store/a3al4xgkxqp4w718d5ai4nhrk4blm6am-simdjson-4.6.4', '/nix/store/dphsh3jff8w6n9p3xbfmkia5krqwv52f-glibc-2.42-103']}, '/nix/store/ai689c7gfx1ka7fwarc4vc0cm70ahdfp-icu4c-78.3': {'nar_hash': 'sha256-2b4JpaeEInzkviIzdxI5IvPPndtVTZZiiQGr8bBTqlc=', 'references': ['/nix/store/0ba5kj6r0zhfwd84l5vzccqvx7amlq2c-gcc-15.3.0-lib', '/nix/store/ai689c7gfx1ka7fwarc4vc0cm70ahdfp-icu4c-78.3', '/nix/store/dphsh3jff8w6n9p3xbfmkia5krqwv52f-glibc-2.42-103']}, '/nix/store/acyqmf1mm0r2hq8xv2sckficwp3dg9qb-icu4c-78.3-dev': {'nar_hash': 'sha256-3iQr+b6vdPc7TFxU5LclMDRZMSgUPXUu1ZuhS9MK3Rk=', 'references': ['/nix/store/0ba5kj6r0zhfwd84l5vzccqvx7amlq2c-gcc-15.3.0-lib', '/nix/store/acyqmf1mm0r2hq8xv2sckficwp3dg9qb-icu4c-78.3-dev', '/nix/store/ai689c7gfx1ka7fwarc4vc0cm70ahdfp-icu4c-78.3', '/nix/store/dphsh3jff8w6n9p3xbfmkia5krqwv52f-glibc-2.42-103', '/nix/store/hc49zakwkkyp9zlyl80b71jhxkpn4hsx-bash-5.3p9', '/nix/store/kwc34h21my8mf7xbqm9gxs1xfx07xb4i-coreutils-9.11']}, '/nix/store/f0lcjigadrvilgw2fprzdd96fw055q0b-openssl-3.6.5-dev': {'nar_hash': 'sha256-HFI+2XtYtlzGAKc0booLunYPI1in2E7PkpnMKwY4W4E=', 'references': ['/nix/store/f0lcjigadrvilgw2fprzdd96fw055q0b-openssl-3.6.5-dev', '/nix/store/fya253x5ky7rhfz6rkgdwjr1fzf7fy71-openssl-3.6.5-bin', '/nix/store/q1fgk31hkgl8a7znhmvb0bq8bbcaf64y-openssl-3.6.5']}, '/nix/store/gi9gff3ir00m9j7z801w5fxi9r91axjw-brotli-1.2.1': {'nar_hash': 'sha256-H4ljczDn5b4I/2cL+S9AHoZEE2m+MbJMs2b8WfUYBDg=', 'references': ['/nix/store/2l6kf3nfwb4k9c5dsdg8k1fs2jr5qikb-brotli-1.2.1-lib', '/nix/store/dphsh3jff8w6n9p3xbfmkia5krqwv52f-glibc-2.42-103']}, '/nix/store/hmqgi0grd4ckdyj81bbry6kgqkkha9vs-brotli-1.2.1-dev': {'nar_hash': 'sha256-n0Uo0Pu5/oSv2NpKzYMB9pXGmEIQv2Zr4Q5dHdSiQr4=', 'references': ['/nix/store/2l6kf3nfwb4k9c5dsdg8k1fs2jr5qikb-brotli-1.2.1-lib', '/nix/store/gi9gff3ir00m9j7z801w5fxi9r91axjw-brotli-1.2.1', '/nix/store/hmqgi0grd4ckdyj81bbry6kgqkkha9vs-brotli-1.2.1-dev']}, '/nix/store/i4w1mj6rawirh6m26k8d9hpcjmrgd3pp-zlib-1.3.2-dev': {'nar_hash': 'sha256-Q8/leRme5dX3DRBhUiqfXMFi9gpsAcfpQrsP8hu0tvM=', 'references': ['/nix/store/4k9dyzhafi9dn1qss1aikjrn1flkbvq9-zlib-1.3.2-static', '/nix/store/7b063z98zcilpmzj2sz7sl56gl84zf02-zlib-1.3.2', '/nix/store/i4w1mj6rawirh6m26k8d9hpcjmrgd3pp-zlib-1.3.2-dev']}, '/nix/store/kymjrr0lbkbjxzlz0pphdazryyklg754-merve-1.2.2': {'nar_hash': 'sha256-2SLBNl244MF7FkwHul3QHAdIQkuwiK5wOB4uf9de2d4=', 'references': ['/nix/store/0ba5kj6r0zhfwd84l5vzccqvx7amlq2c-gcc-15.3.0-lib', '/nix/store/dphsh3jff8w6n9p3xbfmkia5krqwv52f-glibc-2.42-103', '/nix/store/kymjrr0lbkbjxzlz0pphdazryyklg754-merve-1.2.2']}, '/nix/store/wcrbb004ci15dp5d3chhk5kzfdbc22g9-libuv-1.52.1': {'nar_hash': 'sha256-46kugxc0YpnRV73KdVSTSArXeuhI+2GGHnudjrxbF0g=', 'references': ['/nix/store/dphsh3jff8w6n9p3xbfmkia5krqwv52f-glibc-2.42-103', '/nix/store/wcrbb004ci15dp5d3chhk5kzfdbc22g9-libuv-1.52.1']}, '/nix/store/xnyn6xlh1kk09parg7sgsqcc7sa7hh28-libuv-1.52.1-dev': {'nar_hash': 'sha256-ovsMn2SJ9zTxQN9DMoeFW03XN6vz1abgNBixYZdEQW8=', 'references': ['/nix/store/wcrbb004ci15dp5d3chhk5kzfdbc22g9-libuv-1.52.1', '/nix/store/xnyn6xlh1kk09parg7sgsqcc7sa7hh28-libuv-1.52.1-dev']}, '/nix/store/nnqg2qvmax2dd36679aplxgs5zn072qv-uvwasi-0.0.23': {'nar_hash': 'sha256-GYRCeTKMigvmyJKDmm8XGjJruf7ra7QAMQT53+8ZyeI=', 'references': ['/nix/store/dphsh3jff8w6n9p3xbfmkia5krqwv52f-glibc-2.42-103', '/nix/store/nnqg2qvmax2dd36679aplxgs5zn072qv-uvwasi-0.0.23', '/nix/store/wcrbb004ci15dp5d3chhk5kzfdbc22g9-libuv-1.52.1', '/nix/store/xnyn6xlh1kk09parg7sgsqcc7sa7hh28-libuv-1.52.1-dev']}, '/nix/store/wzng3jzfjfk4j0i2y4w6crknydhmx588-c-ares-1.34.9': {'nar_hash': 'sha256-spK0UnhwPHhe1ZOnO34mR78i30uTtO9/tUfzNmE0Tsk=', 'references': ['/nix/store/dphsh3jff8w6n9p3xbfmkia5krqwv52f-glibc-2.42-103', '/nix/store/wzng3jzfjfk4j0i2y4w6crknydhmx588-c-ares-1.34.9']}, '/nix/store/pqv9xk93w9pkpj2s5w373nmisr65jm5c-c-ares-1.34.9-dev': {'nar_hash': 'sha256-bn8NV87vT/MLnQ378TEamwYicWSaoVGWegDGfZ58sC4=', 'references': ['/nix/store/pqv9xk93w9pkpj2s5w373nmisr65jm5c-c-ares-1.34.9-dev', '/nix/store/wzng3jzfjfk4j0i2y4w6crknydhmx588-c-ares-1.34.9']}, '/nix/store/zkkfmzdlzwj06fi70qfwx6ky8f8xh670-sqlite-3.53.3-bin': {'nar_hash': 'sha256-yRhaHwUAY2Kjn2g+XUu2dMoZ+qBNuSvp2B22nBal9Ks=', 'references': ['/nix/store/7b063z98zcilpmzj2sz7sl56gl84zf02-zlib-1.3.2', '/nix/store/dphsh3jff8w6n9p3xbfmkia5krqwv52f-glibc-2.42-103']}, '/nix/store/qdm1gxkdmb5jdcv72mjql8j9h54j84sn-sqlite-3.53.3-dev': {'nar_hash': 'sha256-Hoyfkp4BSskZ8QNgGBuI4qNt7tYL9p1zOI4zjGXmP9A=', 'references': ['/nix/store/4qqwpd1f34k9505ljggkh07p5a9pllsz-sqlite-3.53.3', '/nix/store/qdm1gxkdmb5jdcv72mjql8j9h54j84sn-sqlite-3.53.3-dev', '/nix/store/zkkfmzdlzwj06fi70qfwx6ky8f8xh670-sqlite-3.53.3-bin']}, '/nix/store/yw17brhraxrgq2wj4j6ibhhincxkz6bc-zstd-1.5.7-bin': {'nar_hash': 'sha256-Oa/zHakVtey4XUh+SRIbkA25B+eNRqbjUoBzwwYjOkQ=', 'references': ['/nix/store/0ba5kj6r0zhfwd84l5vzccqvx7amlq2c-gcc-15.3.0-lib', '/nix/store/7348w7xcmpri6ajymnp136w2hkz1mdwx-zstd-1.5.7', '/nix/store/dphsh3jff8w6n9p3xbfmkia5krqwv52f-glibc-2.42-103', '/nix/store/hc49zakwkkyp9zlyl80b71jhxkpn4hsx-bash-5.3p9', '/nix/store/pbxald1gihb1bl9l30j764q0ibb55421-gnugrep-3.12', '/nix/store/yw17brhraxrgq2wj4j6ibhhincxkz6bc-zstd-1.5.7-bin']}, '/nix/store/x735fzw5abldd4sk10lasz1dkayi3bwr-zstd-1.5.7-dev': {'nar_hash': 'sha256-k8m2BeZjFgGJGTyaHMCsQb4w11a4fJVAOUQItySuGPg=', 'references': ['/nix/store/7348w7xcmpri6ajymnp136w2hkz1mdwx-zstd-1.5.7', '/nix/store/x735fzw5abldd4sk10lasz1dkayi3bwr-zstd-1.5.7-dev', '/nix/store/yw17brhraxrgq2wj4j6ibhhincxkz6bc-zstd-1.5.7-bin']}}}
CURRENT = '/nix/store/phi68cwg38madbq8p805yvrsyry8g8wr-nixos-system-srv1982677-26.05pre-git'
DIRECTORY = Path('/var/lib/mrjam-deployment-delivery/ci-host-Q-import-002-20261103')
STATE = Path('/var/lib/mrjam-cutover/first-deployment')
RESULT_DIRECTORY = Path('/run/mrjam-first-release-status-05')
STORE = re.compile(r'/nix/store/[0-9abcdfghijklmnpqrsvwxyz]{32}-[A-Za-z0-9+._?=-]{1,200}\Z')
NAR = re.compile(r'sha256-[A-Za-z0-9+/]{43}=\Z')


class Refused(RuntimeError):
    pass


def require(value):
    if not value:
        raise Refused('POSTRELEASE_CODE_IMPORT_REFUSED')


def parse(raw):
    def unique(items):
        value = {}
        for key, item in items:
            require(key not in value)
            value[key] = item
        return value
    return json.loads(raw, object_pairs_hook=unique)


def validate_release(value):
    require(type(value) is dict and set(value) == {
        'schema_version', 'export_sha256', 'export_bytes', 'required_free_bytes', 'artifacts'})
    require(type(value['schema_version']) is int and value['schema_version'] == 1)
    require(type(value['export_sha256']) is str and re.fullmatch('[0-9a-f]{64}', value['export_sha256']))
    require(type(value['export_bytes']) is int and 0 < value['export_bytes'] <= 1024**3)
    require(type(value['required_free_bytes']) is int
            and 2 * value['export_bytes'] + 1024**3 <= value['required_free_bytes'] <= 8 * 1024**3)
    artifacts = value['artifacts']
    require(type(artifacts) is dict and 0 < len(artifacts) <= 10000)
    for path, info in artifacts.items():
        require(type(path) is str and STORE.fullmatch(path))
        require(type(info) is dict and set(info) == {'nar_hash', 'references'})
        require(type(info['nar_hash']) is str and NAR.fullmatch(info['nar_hash']))
        refs = info['references']
        require(type(refs) is list and len(refs) <= 4096 and refs == sorted(set(refs)))
        require(all(type(item) is str and STORE.fullmatch(item) for item in refs))
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
    # Only this fixed, bound public code archive can be replaced on retry.
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
        os.rename("export.partial","export.nar",src_dir_fd=directory,dst_dir_fd=directory)
        os.fsync(directory)
    finally:
        os.close(fd)


def private_json(directory, name, maximum):
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK, dir_fd=directory)
    with os.fdopen(fd, 'rb') as stream:
        item = os.fstat(stream.fileno())
        require(stat.S_ISREG(item.st_mode) and item.st_uid == item.st_gid == 0
                and item.st_nlink == 1 and stat.S_IMODE(item.st_mode) == 0o600)
        raw = stream.read(maximum + 1)
    require(len(raw) <= maximum)
    return parse(raw)


def gate(state):
    require(all(os.path.realpath(path) == CURRENT for path in ('/run/current-system', '/nix/var/nix/profiles/system')))
    phase = private_json(state, 'phase.json', 1024)
    require(type(phase) is dict and set(phase) == {'schema_version', 'phase', 'elapsed_seconds'}
            and type(phase['schema_version']) is int and phase['schema_version'] == 1
            and phase['phase'] == 'public-writes-open' and type(phase['elapsed_seconds']) is int
            and phase['elapsed_seconds'] >= 0)
    result_directory = protected_directory(RESULT_DIRECTORY)
    try:
        result = private_json(result_directory, 'result.json', 1024)
        require(type(result) is dict and type(result.get('schema_version')) is int
                and result == {'schema_version': 1, 'code': 'CUTOVER_VERIFIED', 'phase': 'public-writes-open'})
    finally:
        os.close(result_directory)


def command(args, source=None):
    process = None
    try:
        process = subprocess.Popen(args, stdin=source if source is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, start_new_session=True,
            env={'LANG': 'C', 'LC_ALL': 'C', 'NIX_PATH': ''})
        data = bytearray()
        end = time.monotonic() + 240
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while True:
                remaining = end - time.monotonic()
                require(remaining > 0 and selector.select(remaining))
                chunk = os.read(process.stdout.fileno(), 16384)
                if not chunk:
                    break
                data.extend(chunk)
                require(len(data) <= 2 * 1024**2)
        require(process.wait(timeout=max(.01, end - time.monotonic())) == 0)
        return bytes(data)
    finally:
        if process is not None:
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=1)
            process.stdout.close()


def verify_import(release, imported):
    observed = imported.decode('ascii').splitlines()
    paths = sorted(release['artifacts'])
    require(len(observed) == len(set(observed)) and set(observed) == set(paths))
    command([CURRENT + '/sw/bin/nix-store', '--verify-path', *paths])
    info = parse(command([CURRENT + '/sw/bin/nix', '--extra-experimental-features', 'nix-command',
                          'path-info', '--json', *paths]))
    if type(info) is list:
        require(all(type(item) is dict and type(item.get('path')) is str for item in info))
        require(len({item['path'] for item in info}) == len(info))
        info = {item['path']: item for item in info}
    require(type(info) is dict and set(info) == set(paths))
    for path in paths:
        require(type(info[path]) is dict and info[path].get('narHash') == release['artifacts'][path]['nar_hash']
                and sorted(info[path].get('references', [])) == release['artifacts'][path]['references'])


def deliver(release, stream):
    release = validate_release(release)
    require(os.geteuid() == os.getegid() == 0 and os.uname().nodename == 'srv1982677')
    state = protected_directory(STATE)
    lock = work = None
    try:
        lock = os.open('transaction.lock', os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=state)
        item = os.fstat(lock)
        require(stat.S_ISREG(item.st_mode) and item.st_uid == item.st_gid == 0
                and item.st_nlink == 1 and stat.S_IMODE(item.st_mode) == 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        gate(state)
        work = protected_directory(DIRECTORY, create=True)
        require(stat.S_IMODE(os.fstat(work).st_mode) == 0o700)
        fcntl.flock(work, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for filesystem in (os.fstatvfs(work), os.statvfs('/nix/store')):
            require(filesystem.f_bavail * filesystem.f_frsize >= release['required_free_bytes'])
        binding = (json.dumps(release, sort_keys=True, separators=(',', ':')) + '\n').encode()
        try:
            fd = os.open('release.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                         0o600, dir_fd=work)
        except FileExistsError:
            require(private_json(work, 'release.json', 2 * 1024**2) == release)
        else:
            with os.fdopen(fd, 'wb') as output:
                output.write(binding)
                output.flush()
                os.fsync(output.fileno())
            os.fsync(work)
        receive(stream, work, release)
        gate(state)
        fd = os.open('export.nar', os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=work)
        with os.fdopen(fd, 'rb') as archive:
            imported = command([CURRENT + '/sw/bin/nix-store', '--import'], source=archive)
        verify_import(release, imported)
        gate(state)
    finally:
        if work is not None:
            os.close(work)
        if lock is not None:
            os.close(lock)
        os.close(state)
    return {'schema_version': 1, 'code': 'POSTRELEASE_CODE_IMPORTED', 'store_paths': len(release['artifacts']),
            'application_activation': False, 'systemd_changes': False}


def main():
    try:
        require(len(sys.argv) == 1)
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        os.umask(0o077)
        signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(Refused()))
        signal.alarm(600)
        value = deliver(RELEASE, sys.stdin.buffer)
    except Exception:
        print('{"schema_version":1,"code":"POSTRELEASE_CODE_IMPORT_REFUSED"}')
        return 1
    finally:
        signal.alarm(0)
    print(json.dumps(value, sort_keys=True, separators=(',', ':')))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
