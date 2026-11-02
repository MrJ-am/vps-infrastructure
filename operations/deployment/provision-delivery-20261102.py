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

RELEASE = {'schema_version': 1, 'export_sha256': '7d7eb4d466bbb0a691f8bf39d00df4bdf446ee4b96d334c4ad524e1e01e477e9', 'export_bytes': 718957480, 'required_free_bytes': 2552486824, 'store_paths': ['/nix/store/00xp873b65inf04i1v9b46zkdqwszlp4-gmp-with-cxx-6.3.0', '/nix/store/07j8s1c7qnlkdi1dk2zvjh3wp65ykb3d-pcsclite-2.4.1-lib', '/nix/store/07rb9bnzmmpah26nwz1q14bbkjmkhglc-kexec-tools-2.0.32', '/nix/store/0ba5kj6r0zhfwd84l5vzccqvx7amlq2c-gcc-15.3.0-lib', '/nix/store/0c9jfzpjfh1d5ibzvwprn8qpb6z6sl61-lz4-1.10.0-lib', '/nix/store/0q9vgj48awrcm6l14fccdbjjqsbmh921-libcap-ng-0.9.3', '/nix/store/0xiinbh7pbj479i5v28mqnjrvhvbdibf-systemd-260.2', '/nix/store/10d0lpvg6pxnzlgnrdpm3xjyki00zgah-gdbm-1.26-lib', '/nix/store/13czpvp88x852739v5xi04s871pn35b5-bash-interactive-5.3p9', '/nix/store/14cfdqp8w2iw188vhjfaz2wg8pzbghp3-openssl-3.6.3', '/nix/store/16xnz1c5dc4nazkb3k5w2xhpmi5qnbhf-kmod-31-lib', '/nix/store/1d733bdg61s0qwwr04xiyrqz4wydv3ym-xz-5.8.4', '/nix/store/2ildinmf7h8a4vl97m2rdii4n6n0vm0j-lvm2-2.03.39-lib', '/nix/store/2ilkb5g4armlzzp19kzr2g553mgvrg7f-libtasn1-4.21.0', '/nix/store/2l6kf3nfwb4k9c5dsdg8k1fs2jr5qikb-brotli-1.2.1-lib', '/nix/store/2llb0qaa9lbwli6i0350vy3j4jkhmbmg-libseccomp-2.6.1-lib', '/nix/store/31f225xam9v06jnm4878id3ch2wjkgkl-keyutils-1.6.3-lib', '/nix/store/31qzjx1vrkwcrl4zlhiarn2y9ynpyxr5-libseccomp-2.6.1-lib', '/nix/store/3lzmjbp0wxj4bjmaj286n2dyfkd49wr3-gnutls-3.8.13', '/nix/store/3syvw6qrdv5bpnqkjirvjp1idnfb8b7r-libapparmor-4.1.7', '/nix/store/3yhivr3h6801yk7sy3skzj4f2j86i68r-readline-8.3p3', '/nix/store/41b4nygazaawgbags71flx463x4426kf-glibc-locales-2.42-67', '/nix/store/41xwpwwpg8jxqgar1jf9lww0xkfy9mjc-ngtcp2-1.22.1', '/nix/store/4fhm41clh7s82xgb3jdnpll1axi9zqgq-xgcc-15.3.0-libgcc', '/nix/store/4l0jkaf7zavzdyjbqzi39cyk1j9ds8g2-p11-kit-0.26.2', '/nix/store/4qhmizki1n0i0rp64203wnqff73anv8l-audit-4.2.1-lib', '/nix/store/4qqwpd1f34k9505ljggkh07p5a9pllsz-sqlite-3.53.3', '/nix/store/4whvlsd07mc0rrkpdinhnhgixrzk7lkv-ncurses-6.6', '/nix/store/4xyis60wzqx4ib55rwh9x3997p2s8ngx-libcbor-0.13.0', '/nix/store/5055c2cpww9vrjz27yvhssagf1hd5ah6-attr-2.6.0', '/nix/store/51hyxk9wipkgfjaj73c9w8a4biip99l8-xz-5.8.3', '/nix/store/56vgzbxd1k167sq900dnlp7lldcmznl3-libxml2-2.15.4', '/nix/store/5yqv8fsy6qhw45qs53qnirib9vl3cjhq-mrjam-kanidm-worker-provision-2', '/nix/store/64r3qy45dngms51i718ddna9p08lczd2-kanidm-1.11.2', '/nix/store/6cyzyibzva7cnys2adj9z8lbqd3xz034-kexec-tools-2.0.32', '/nix/store/6ds9j3mi4y409fdyqf5z3scrsfcfyl4i-cracklib-2.10.3', '/nix/store/6rmlfwsnc8320am0wndc12rhqqm3llzr-json-c-0.18', '/nix/store/7348w7xcmpri6ajymnp136w2hkz1mdwx-zstd-1.5.7', '/nix/store/7b063z98zcilpmzj2sz7sl56gl84zf02-zlib-1.3.2', '/nix/store/7g49xp4rs061vp7ilphib3x6hy693qja-libapparmor-4.1.7', '/nix/store/7vbcc5c5fy1ff8hmaca05px0n0l1gj1x-db-4.8.30', '/nix/store/8pcfawggcwjikaq2mw24d6a58gyaykxc-dns-root-data-2025-04-14', '/nix/store/8r9awlc6p0i47vr34p4j11sbgq4mi9bv-mailcap-2.1.54', '/nix/store/8rgv6y4hsjfjj80582gzswhi6ld10942-libtpms-0.10.2', '/nix/store/8x4winzarl3q48vfjkpfrsdl6wj68bny-libmicrohttpd-1.0.10', '/nix/store/91k9r1ksqdan1dnc8kmkdv29cwbr2b6h-kmod-31-lib', '/nix/store/9krwrb9a6b9kmqlfh0gdv0g73mq81if4-libfido2-1.17.0', '/nix/store/9s979hn0m0bn4r03xggga0pcd4diny7b-kbd-2.9.0', '/nix/store/9v95cv7bjjv4admfqxrvcxlvjk3k638k-nettle-3.10.2', '/nix/store/9wdq1zinil9w64n9asv6haxyis1php6c-publicsuffix-list-0-unstable-2026-05-13', '/nix/store/a6d8x05xvrafdg2l8v118sv8jcg25x01-json-c-0.18', '/nix/store/aadqqqrfvi7mdnk28h366irf6f1s09mb-systemd-minimal-libs-260.2', '/nix/store/ahni4ky7vcyga5rkfk6yil6g0293qyvk-kmod-31', '/nix/store/akmhgr98bcg2nrnls89gl7xz282h1mzf-mpdecimal-4.0.1', '/nix/store/alffmd3v47nm00x625pwa5viq4z8kbx6-brotli-1.2.0-lib', '/nix/store/am2hi8dgk0qfngq41nvr4835m19b68j8-zstd-1.5.7', '/nix/store/arlgrwqkfrxmvl39wzdkq760ih6pajvl-unbound-1.26.0-lib', '/nix/store/bddz6wynx2d6cs66d9b32qsw26s6wavw-libbpf-1.7.0', '/nix/store/br4ikmi388vrj4bf8kd9nb3k2kiqprc0-libffi-3.8.0', '/nix/store/brrzhh73q6h5c17gi3004svz8659aj52-curl-8.21.0', '/nix/store/c37jpglrjhdp4y3dkq7g5s8qshv43jnj-elfutils-0.194', '/nix/store/c4f8bfak9m1z7210rkdhz2gl9dggk9vh-util-linux-minimal-2.42.2-login', '/nix/store/cg5lp7fwxzib30f6b2lm63p5bd791j6h-acl-2.4.0', '/nix/store/chjqgz96k80r4nxzsiir5gx93iva2w4z-libevent-2.1.13', '/nix/store/clr3gc8bxn467jqa9073rl9c4vg7pfyq-cryptsetup-2.8.6', '/nix/store/cvv2iqql2vijlyxvfrijhzq7bvzvbwdl-elfutils-0.194', '/nix/store/d2vjl55mqymp5pqk9nshrdx89965fcxx-nghttp3-1.15.0', '/nix/store/d3f8rpj3iy1wx2p2d8fxqab8kdygyi9f-util-linux-minimal-2.42.4-lib', '/nix/store/ddfagd4llkbv8p3cblpa3bxvn6l538yl-systemd-minimal-libs-260.5', '/nix/store/dj6hfwqfynzvy7fp6qc9dwhwxvl71ixd-pcre2-10.49', '/nix/store/dphsh3jff8w6n9p3xbfmkia5krqwv52f-glibc-2.42-103', '/nix/store/dv9ai2cb4dvaq6a8ajgyyxdjcqjg49hs-qrencode-4.1.1', '/nix/store/dwdl7pb826zq929sjdksq60wdmblpdxa-tpm2-tss-4.2.0', '/nix/store/ffrfb5cybny94sn2gsxxxvg8rqzl2adv-libcap-ng-0.9.3', '/nix/store/fp6wnyklwzdncp0nvhdy9d5fnir0mjq5-libunistring-1.4.2', '/nix/store/fsvi4zsx8w4ddbdhx0x7mijs3y4dkkc5-libgpg-error-1.59', '/nix/store/fyp5g3kpfiiaxw9lsbakxms2ll4q8a8d-libpwquality-1.4.5-lib', '/nix/store/g5vv20l7ydhw8kaqfzbnbr2qdbmfilpp-dns-root-data-2025-04-14', '/nix/store/gph17gb73p6qbrqqjnypfjj5npf0ldyx-coreutils-9.11', '/nix/store/h6hijkdsxd2cpbma09cw6wjkkfnxkcjc-cryptsetup-2.8.6', '/nix/store/hc49zakwkkyp9zlyl80b71jhxkpn4hsx-bash-5.3p9', '/nix/store/hl2q8nksy0m8qgh3hzvd24rhill1rpix-libunistring-1.4.2', '/nix/store/hlki0nb8yfbvb67bam4sqns33h0mw02y-keyutils-1.6.3-lib', '/nix/store/hnz82d47sah31rhskabkpjimz5pwzpkm-libarchive-3.8.9-lib', '/nix/store/hy66nai3pdjgzhv584c0j6di0y087kdb-krb5-1.22.2-lib', '/nix/store/iw7ljvmirxgjxpii7zhkxikiaq5vbqz9-gmp-with-cxx-6.3.0', '/nix/store/j10w6scxbw4vfhxv2s2crd9nc3i9cbcb-libpwquality-1.4.5-lib', '/nix/store/j1axc9lgzg1gx08z3vmjrwkvyib9a0l5-nghttp2-1.69.0-lib', '/nix/store/j5m1y5k6qp5iwb23j5k6w2y8ffv9lxvl-pcre2-10.46', '/nix/store/jd0bvwh4bhkbgr29p4xrjb0vr73hj11p-libbpf-1.7.0', '/nix/store/jq0mamb7v8ly6gxyrq8fnrs7al0l3cdp-libssh2-1.11.1', '/nix/store/jwq26byp7q4mxqg3yqqq4vgsabs7yknm-findutils-4.10.0', '/nix/store/k0qnrn1rz01rvc2ys7vcll4wa80qcrdi-expat-2.9.0', '/nix/store/k41vs2nqfvjqv0k91r0xl5iv0nicv2yl-libxcrypt-4.5.2', '/nix/store/k5j2kwjcap1zgdh4xn1fvvlsrzy55g1i-libxcrypt-4.5.2', '/nix/store/k77kpp56p10f5gkdigq288djalcvaj43-util-linux-minimal-2.42.2-mount', '/nix/store/k8rbpjlq071djhghgnxm2kcng6h2b035-gcc-15.2.0-libgcc', '/nix/store/kfpkk6hcmlybxj552fyb625f3089xq4g-libfido2-1.17.0', '/nix/store/khbxm3c02xklnz8jgh4cdikkgz73ssh2-linux-pam-1.7.2', '/nix/store/kp4khgx2g67v63zwgazg99p196s71q6z-lvm2-2.03.39-lib', '/nix/store/kp6p38x6zb21n7gdlnp9nsm2aagq7sg2-python3-3.13.17', '/nix/store/kp7qcdqfxcn1wg2fzszf0x3ra89n4akx-libpsl-0.21.5', '/nix/store/kvdgx9r3ssdsnyrvg2wfv6il4pgvazi5-curl-8.23.0', '/nix/store/kwc34h21my8mf7xbqm9gxs1xfx07xb4i-coreutils-9.11', '/nix/store/kxcgzz6lhrp9b5l3b394haz74g7721id-tpm2-tss-4.2.0', '/nix/store/l68i51npb6nlxi6z18gvgb45dz3xr5yp-zlib-1.3.2', '/nix/store/lczq4f5z4yf2h8v0i2w4jcy4bi43qfbs-bzip2-1.0.8', '/nix/store/lkin0lfzqafiar6l2ay142g17pd7kln9-qrencode-4.1.1', '/nix/store/lrq4wadw7ry4vh0rsnhv7ylshnbld7px-audit-4.2.1-lib', '/nix/store/m07h00fl6538s4gavrp66a20ka4hg7fy-glibc-2.42-67', '/nix/store/m2sv1rizzbnsb35hv3ii0dnf3rvfy3n3-tzdata-2026c', '/nix/store/m905d92wqbq630rz24r8jcfhfizvmn0i-libssh2-1.11.1', '/nix/store/mgf1r7mnba7294pgxycxjly2bl10qvra-nettle-3.10.2', '/nix/store/mgzzwkjcrbvqbi9w7mi4abal8fsh8b1c-db-4.8.30', '/nix/store/mhdban9k5rif6n21v9wqnxpbh9kbq647-libffi-3.8.0', '/nix/store/nbv2zi503h2hjz51qbg44vzs270ffrri-gnutls-3.8.13', '/nix/store/nfl8n4x02qz7v87c9sfc7x52mnhbv9v5-libtpms-0.10.2', '/nix/store/p0znk6v2nv5vwq7kjqylnhv7zskzdhxf-libarchive-3.8.8-lib', '/nix/store/p314bwbyiw87wssqwvxl9y4c3cmmxklj-nghttp2-1.69.0-lib', '/nix/store/p91408xhq9r6sgqkn2ad5kwlnkkg3pfi-libgcrypt-1.12.4-lib', '/nix/store/pasan74z25zzwfnkwb549ayzcamjn593-util-linux-minimal-2.42.4-mount', '/nix/store/pcxd79slak3wdi1kzkyzzcpcy82sarzs-tzdata-2026e', '/nix/store/phlf36lhfwaafls84mxvffp8wpz741jn-attr-2.6.0', '/nix/store/pi4h22d7id0z6hjjf7jg6djbbhszb379-libxml2-2.15.3', '/nix/store/plshlafrnmfk1rsx9cinsg3jisdzzh0s-kmod-31', '/nix/store/pp5x67y8iy6wj09xndk4grjgjdizbw24-gmp-with-cxx-6.3.0', '/nix/store/q1fgk31hkgl8a7znhmvb0bq8bbcaf64y-openssl-3.6.5', '/nix/store/qmv8a98nqp4bpq29z6xsw3fw56m8zfq6-libcbor-0.13.0', '/nix/store/r342d1ndm1sb442i436kzp9pvj7sp5y8-libgpg-error-1.59', '/nix/store/rc22ay9is2cdbmsqi62hvc5l1i33w5bd-p11-kit-0.26.2', '/nix/store/rdw0n35z6xhipyiq6sc8qv0mg7vrldaj-xgcc-15.2.0-libgcc', '/nix/store/s45snyx4414z3q1ycj63qh40hqhhs5yr-gmp-with-cxx-6.3.0', '/nix/store/sacz532zgiacvg7mva9v6gbfmyw427i3-gnugrep-3.12', '/nix/store/scgsymw7hbvk6hh2cgbdz906iv4v5y9z-libidn2-2.3.8', '/nix/store/sm2shwni12x7nv6d3n4j4gzzrvanygwh-kbd-2.9.0', '/nix/store/spghpxf37g1lnkmlrx7kj7k8i9hazvkl-libevent-2.1.13', '/nix/store/spyq8j3kdj6dlbhv5nbnr7a15nficin9-acl-2.4.0', '/nix/store/ss2d4klaskmpg7sd1krwrd18m58lxymz-util-linux-minimal-2.42.2-swap', '/nix/store/svl89366pvzz5s3myh1fjniz9l0x17fh-gnused-4.10', '/nix/store/swqbs9wpaldjqg366sifyhglhdvi9xjd-util-linux-minimal-2.42.4-swap', '/nix/store/v3n5aklhc7s1nhj053r6c2lnz7q3nfzy-linux-pam-1.7.2', '/nix/store/v6ibq54l47kz8m62gm5p4dqr8sjgy4c9-krb5-1.22.2-lib', '/nix/store/v82yxvmiqprfsp4sbb80qh9dmgl2vch3-pcsclite-2.4.1-lib', '/nix/store/vd4c701jdbym69njq5ak0bfih88d5w94-libmicrohttpd-1.0.2', '/nix/store/vwwzgbrpk2cddxbhmj3b2569cnf5yilc-libgcrypt-1.12.2-lib', '/nix/store/vzn35cgfpccivnfy42isn0nb125i6xk2-unit-mrjam-kanidm-worker-provision.service', '/nix/store/w46500zpz7rxhr25lcfb0fgs336gwq10-libtasn1-4.21.0', '/nix/store/wkkvmvz3vnbfl3rkf85gp5p5mgp34ak3-gcc-15.3.0-libgcc', '/nix/store/x8ahakmx4pb07rikx4zi25daih9wrsyf-bzip2-1.0.8', '/nix/store/xharm39n4viqb8d6lbmwynlnx2ih8zr2-nghttp3-1.15.0', '/nix/store/xidgjdv05b8yz6w6qrhk4mmjxm4l2zjf-libidn2-2.3.8', '/nix/store/y3ffb695c582gx3cbd0s2jhs990bkd8z-util-linux-minimal-2.42.4-login', '/nix/store/y3fqx697649kqv1a9c0z1jsk4wy2zlqa-systemd-260.5', '/nix/store/ybmv0g5xva0wn18zdgxz25bm939lmwlq-lz4-1.10.0-lib', '/nix/store/yh0kaqv6a2z8ck3i55syqmwvzq4b74h7-cracklib-2.10.3', '/nix/store/yishn4jrfiyvh63w7cb1wl01mq4wclag-libpsl-0.21.5', '/nix/store/ylm8cvvqs455m3cnfqlx08hh8k81ijj0-ngtcp2-1.22.1', '/nix/store/z0n70pxyzi87why1bcq81zgd7b924nfj-gcc-15.2.0-lib', '/nix/store/z5zjp72jg5yzjvrgs7h7pb0ld5ac1r3m-util-linux-minimal-2.42.2-lib', '/nix/store/z8ichxh35939ky77d5cpwiafwcwdps7d-unbound-1.26.2-lib', '/nix/store/zifx9q7kjslmajccpv3hwrw2v9n27kdd-publicsuffix-list-0-unstable-2026-05-13'], 'package': '/nix/store/5yqv8fsy6qhw45qs53qnirib9vl3cjhq-mrjam-kanidm-worker-provision-2', 'unit_store': '/nix/store/vzn35cgfpccivnfy42isn0nb125i6xk2-unit-mrjam-kanidm-worker-provision.service', 'unit_sha256': '5da6a1e0d958e789aee8bcd19da862c8d7d53641dc35d8c1a7738ad6a5a2cf7d'}
PREVIOUS = "/nix/store/jn9rf2fgk2y6dbhdnjwkmfww3pchkyb9-nixos-system-nixos-26.05.8639.c5c4a43b0e80"
DIRECTORY = Path("/var/lib/mrjam-deployment-delivery/provision-20261102")
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
