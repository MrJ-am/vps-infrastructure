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

RELEASE = {'schema_version': 1, 'export_sha256': '5e68bdb44eab6d854be00b38f9ecec3a6d65b7a00158406b9dc601c1687205fd', 'export_bytes': 339905864, 'required_free_bytes': 1753553552, 'artifacts': {'/nix/store/g9j71wl28a0c63w58vg3jrpkmpp45fl3-system-path': {'nar_hash': 'sha256-yW45G9g+uyh+hg39xSQzgjgtVoKQkBjvzcZxIq3pQHM=', 'references': ['/nix/store/01s1nxfkmy04kyn0x5sjgbdp5malwvw8-shadow-4.19.4-man', '/nix/store/02y6jiffv1m9fn9kl3wqnf44486y7fk0-sudo-1.9.17p2-doc', '/nix/store/055skq6qnzl8pyhhzycp25nlnz4dy547-iptables-1.8.13', '/nix/store/0ivdry0sgr9nwwcy3mqjj16yzh44ihpn-attr-2.6.0-man', '/nix/store/0vl4nm116sqikp0dmfc4h70a6jh3yinm-gnugrep-3.12-info', '/nix/store/0xiinbh7pbj479i5v28mqnjrvhvbdibf-systemd-260.2', '/nix/store/0xml3ipsrjdp9sms6igsw46bzwaqwbr8-postgresql-and-plugins-17.11', '/nix/store/0zffwpbgk5vqkl6by6jjm6w3dq5m40mq-gnused-4.10-info', '/nix/store/16zf71lpbk4xpg9kg7ahlvldgh5qdj3g-dosfstools-4.2-doc', '/nix/store/1735f8fvyf17ss95rcwhwpqnqqrnygh0-nixos-manual-html', '/nix/store/17g9d8hnj52sb0chdd7a7wcicg187w0h-fuse-3.17.4-bin', '/nix/store/1nm0pc53r4ph07s6v9pg5mhmg83nij1z-libcap-2.77-man', '/nix/store/1xg152cbnwliq3fznc5phb454cbqxgp8-nixos-configuration-reference-manpage', '/nix/store/2722ncq58c1amdv6g6nv5d1wvab30p0r-gzip-1.14', '/nix/store/28hprrw9sdi4iarzyxa3r1a22b3dq5pn-openssh-10.5p1', '/nix/store/2ha8gdicpkkcj877kzfqmqgv36zy0za6-fuse-2.9.9-man', '/nix/store/2j6apy7g6f6f4vm69343zd65vwn36kws-xz-5.8.3-man', '/nix/store/2q4qxw870fsgsaddw9jl3mz400564al3-less-692', '/nix/store/2xkiz5q7fpk615dda7480vcqg8qm4p03-nano-9.2-info', '/nix/store/3hsbl2ly5bmh3w7jy8d36mfk18h9qrqc-nix-2.34.8-man', '/nix/store/3llrnwchkvcxgnrr604fhkvcmrlbrk2q-e2fsprogs-1.47.4-bin', '/nix/store/3s8q7nymprzywiiwqp1q9cg3ppzrv9gs-strace-7.2-man', '/nix/store/41b4nygazaawgbags71flx463x4426kf-glibc-locales-2.42-67', '/nix/store/49ma9vimj6wlsbrhqsra6g6fzvsj6shh-ncurses-6.6', '/nix/store/4i5qv49fbdpdlgna7adhslkd3rzwpjh8-diffutils-3.12-info', '/nix/store/4ipi0c4rk72mg5kjlarhaib2d2icx2zm-libressl-4.2.1-nc', '/nix/store/4n075ll5jdwbjv142yg8ymz5f3yf4pam-util-linux-2.42.2-bin', '/nix/store/4zi719k7jdkvcs8nx9kzf3nmilmbhn6i-lvm2-2.03.39-man', '/nix/store/52k47shyn682b1blwrryiha1inib69gq-dbus-broker-37', '/nix/store/5ckqfb66kj5g68d51wgvjknb4hi8fi0z-procps-4.0.6', '/nix/store/5hp4jcqfl8skwm9x3zvvnbc0hgxq9lgn-nextcloud-occ', '/nix/store/5yqv8fsy6qhw45qs53qnirib9vl3cjhq-mrjam-kanidm-worker-provision-2', '/nix/store/60c7245nz0q8qdv9dl9d4nnppxs0lncs-hostname-hostname-debian-3.25', '/nix/store/692yciygdkaw67y9xrgnzzm5lpw9dims-less-692-man', '/nix/store/6cyzyibzva7cnys2adj9z8lbqd3xz034-kexec-tools-2.0.32', '/nix/store/6d84v2gs9xknjsziciy4c2ggvjhrzpnq-libressl-4.2.1-man', '/nix/store/6w1adb545ayza5syyj4d6xscgn66jcws-patch-2.8', '/nix/store/6y6vabwkv5456xns701qkid8fsy8grlr-nixos-version', '/nix/store/742g5xfszqh87pahd8fgfyx4iwfhmyxs-nix-bash-completions-0.6.8', '/nix/store/745rndb9mpgp6z5312l0n73qb7zh0q1x-curl-8.21.0-man', '/nix/store/7bssl9fh53lcz77ily8sxi89b455x0im-which-2.23', '/nix/store/7mx2y4jcvcninami5vic5hz703ylrhnp-bzip2-1.0.8-bin', '/nix/store/81220alzad19dzxxpx3w8wb8ica0cmm1-getent-glibc-2.42-67', '/nix/store/86lm4hs4jsqli3y9amp86bhfm0g888qn-hicolor-icon-theme-0.18', '/nix/store/8i5gszg3ajmy9wbd0pajj7kwb61x50x1-nixos-generate-config', '/nix/store/8pw5kdjzx1nn962lv5bfc7n2a0v0y8gd-nano-9.2-doc', '/nix/store/8s0h3cly1z8h604mxs2dck4nh3bxplma-bash-interactive-5.3p9-doc', '/nix/store/92k4886r653ks2l6vbn0460iagxk9yrk-linux-pam-1.7.2-doc', '/nix/store/97rjxmrszgl6igkflbz6z02dc1ksrx7v-kbd-2.9.0-man', '/nix/store/9dhf3nq4vki7m85g6vjzg9bpvxv4rvv7-dbus-1.16.2-man', '/nix/store/9gaxb2nwp92amz16s3dpwv6ydvyxv04x-bash-interactive-5.3p9-man', '/nix/store/9gjcj4ndp2akrqx108qwb56jzc7y7zrk-diffutils-3.12', '/nix/store/9hq0przpqbd53cn2mskyj8gc7syp8b67-iptables-1.8.13-man', '/nix/store/9s979hn0m0bn4r03xggga0pcd4diny7b-kbd-2.9.0', '/nix/store/a37jg6ffhyy39ij5dbi5vhw1ypn2c6lr-libcap-2.77-doc', '/nix/store/ag994bfxf4wg90nv66y2j18djc5v34cc-xz-5.8.3-bin', '/nix/store/ahni4ky7vcyga5rkfk6yil6g0293qyvk-kmod-31', '/nix/store/aijb8mbsy8vsdnwkgmx1sv84x4x9pk4i-util-linux-2.42.2-man', '/nix/store/bj0j3d3z8aisa45m4280v136q95nxrmg-dosfstools-4.2-man', '/nix/store/bn633cpsdqmafd1vvcaklnrb03ybh967-gzip-1.14-info', '/nix/store/bsfhj5kxm025lb8iwg6ql542h79fyvsw-attr-2.6.0-bin', '/nix/store/c0xp7r0mwdv1gg6ya3g3xswy18dlyjhp-coreutils-full-9.11', '/nix/store/c1lg2lqk42pd0bfv21axvccadd1d599h-nixos-rebuild-ng-26.05', '/nix/store/c1y22r07g4fypxvjs6pwsr0bsg8kbrhv-coreutils-full-9.11-info', '/nix/store/c86lsichvvg94hg78sd9c3ymyfl1b3rx-nano-9.2-man', '/nix/store/c9x2c80rg7fp90x2jgs2dsyg3bdi56k5-systemd-260.2-man', '/nix/store/cadw2div7carnp00khv1xd9m2f14gh2b-nixos-build-vms', '/nix/store/d7mj74d2nk7180brfj4jv7zclm936f3r-gawk-5.4.1-man', '/nix/store/db0m4lhavxmk171x0z4x4vw3rjgdkjyg-iproute2-7.0.0', '/nix/store/f71dcbq77ra7ghf3v0zn2dnb52wl21f1-attr-2.6.0-doc', '/nix/store/f73gqi9pxkzkd55irax6ky16nf84iv1x-nixos-help', '/nix/store/gdalsnb0bbj02c9vbskyzg4qisdlcf3p-shadow-4.19.4', '/nix/store/gf1apxb5ca7yksq9yhda7hkp5p5f1mmd-iputils-20250605-man', '/nix/store/gripy5dbgwaa7g173vxdm6vr1vwhmk72-nftables-1.1.6', '/nix/store/h1dpxri50hi5llambjar3iqsk5d4723k-lvm2-2.03.39-bin', '/nix/store/hdjzm1if6g9qv71ycbmfimpwvvhvgvlh-kmod-31-man', '/nix/store/hib2p6mijrs78649g9admgaaacyglrxg-e2fsprogs-1.47.4-info', '/nix/store/hiznkmdx8i38b1cyfdkbbhv7wbmqv4c4-jq-1.8.2-doc', '/nix/store/hrcpvvwkzz2i76rh10gxlcylhg3l20bx-jq-1.8.2-man', '/nix/store/hxv34l653mz487v9sps8v62zw52bpkn3-curl-8.21.0-bin', '/nix/store/i49yca49hqyr8kdjzif6h649ywq9vy0y-gzip-1.14-man', '/nix/store/i4bv0lvk0gfzllcy2kqgz3iam0aw4c4i-nix-2.34.8', '/nix/store/i6g163aafjy3wjxqcngvldnpwgjqljp3-gnutar-1.35-info', '/nix/store/j310a1j772b3lszjmxps00704nayqj4f-rsync-3.4.4', '/nix/store/j4irypvykil70289ddhyls9pf1ralc1r-shadow-4.19.4-su', '/nix/store/j6db4k0sk3yylzsb4ab1qqry4dqhn4yj-git-2.54.0-doc', '/nix/store/jfb7bpnyyvpj1nbwvh7nsnay4mmiswsw-nixos-firewall-tool', '/nix/store/jksq0zyk08l29w4alp0g3ycgx6pwwjdk-perl-5.42.0', '/nix/store/jl7nsrjp8a0hpvzck1j3glxmy4ax0n85-acl-2.4.0-man', '/nix/store/jwq26byp7q4mxqg3yqqq4vgsabs7yknm-findutils-4.10.0', '/nix/store/k4a7p2ap87g5a7hvrdxx8ii9fb9fq5if-nixos-install', '/nix/store/khbxm3c02xklnz8jgh4cdikkgz73ssh2-linux-pam-1.7.2', '/nix/store/kybpnrnk5c16hi8s0ac5fjqljfldrj2y-sound-theme-freedesktop-0.8', '/nix/store/l4qnlbca31jvyh0sdg5qqbqkh48z1q19-gnutar-1.35', '/nix/store/l5ca87vbmi6g6p5ddh1gfs2mhygh5096-bind-9.20.26-man', '/nix/store/lgxapskcnrwdyhqhaddbxzminyg4rh2g-findutils-4.10.0-info', '/nix/store/lncccjysbrhk7fsn37v0gkbcqgawl60n-nixos-enter', '/nix/store/lzi4zg1ngjwqfjs0wyjf6bwrcl814mxb-glibc-2.42-67-bin', '/nix/store/m7wg7cj2vw3n6a0pcl3fzbqfm0qsawmd-gawk-5.4.1', '/nix/store/mrkhvxi2v49s0x3sdkbfgdm666cjf8h5-fuse-2.9.9-bin', '/nix/store/n1spp8lk0zzhpf5gsa58skm3wyz69xq0-time-1.10-info', '/nix/store/na08wiwcbhj7r1kllqrvjbc4d5wnsgsi-fuse-3.17.4-man', '/nix/store/nc1v34la9h8d7k1sfhgvsxmq53lxv07q-strace-7.2', '/nix/store/nf5qgqsbj38jrsd6f9l0yqic0v363l2i-iputils-20250605', '/nix/store/nly4cml071i82515r89rpdw38z55wjqd-git-2.54.0', '/nix/store/nwfpj069lh96b4qa1zi3x9l5f7lp9mss-sudo-1.9.17p2-man', '/nix/store/p43451fxbl4hqjgq4ffma4nqbfidpgsy-texinfo-interactive-7.2', '/nix/store/pa58lnaxbmq003l9y7423kknkss0c5qi-mkpasswd-5.6.6', '/nix/store/phvdhap8ylrf7xffpbqlad69faza6mdx-man-db-2.13.1', '/nix/store/pkf547jp8a92k4wmxikkyby58w10pysr-bash-interactive-5.3p9', '/nix/store/plyq7vbh5bbhb4y2si2iryjmig05gk7v-bind-9.20.26-host', '/nix/store/pvh5hvndqbhr9l89ikd7gkqbgjvkf1vq-ripgrep-15.1.0', '/nix/store/q5njfd51xpjgs5yi2vha683fk21s7ww8-ncurses-6.6-man', '/nix/store/q9xs4w9gsyknmzwz8dmrbxydr797gzf7-sudo-1.9.17p2', '/nix/store/qcy7zykkx2ix5asisgfpchcsf6kgafwm-bzip2-1.0.8-man', '/nix/store/ra0v8izly38qdwdm83ba75s27znigw75-acl-2.4.0-bin', '/nix/store/rw7kxdggjwf65ryli7pm5n7mn8vj606i-libcap-2.77', '/nix/store/s4qgc0azvmh9qadkz0mfbfb2rcpy035c-grub-2.12', '/nix/store/sacz532zgiacvg7mva9v6gbfmyw427i3-gnugrep-3.12', '/nix/store/sbflyyw5x1vplljcq58v0wmvr17hjbhc-cpio-2.15', '/nix/store/svl89366pvzz5s3myh1fjniz9l0x17fh-gnused-4.10', '/nix/store/v72gpw6s80x2d632lmb41wp53zxlz1m4-shared-mime-info-2.4', '/nix/store/vkjzswzi7r1ayxa0xr920bjrzmi04x7v-jq-1.8.2-bin', '/nix/store/vl09b1z1d4xcg8fkva7j3d284lnidf46-nano-9.2', '/nix/store/vrr76aq4sph3qlp5x5y9rgrmw69sgaqs-nix-info', '/nix/store/w4dijcw76ql2ll919zdkpl1raah0n1mk-man-db-2.13.1-doc', '/nix/store/w6axsjxghin0znv5yhifr2w3g78ayj8j-openssh-10.5p1-man', '/nix/store/wg5s3dvr0i7prdnkdr3cf9wr6cmbw8x5-acl-2.4.0-doc', '/nix/store/wibagbn66jv9804bcmkmk4qvz49h1mr5-bash-interactive-5.3p9-info', '/nix/store/wkdhd69xwlp5qndajkfl7b8xs0yab0v3-dosfstools-4.2', '/nix/store/xcbnr01clpgvgbdz3vjas9xyww39hdd6-nixos-option', '/nix/store/xd3xlh8fglp15k1nrhwvq5n5qblyghrz-fontconfig-2.17.1-bin', '/nix/store/xp99bvc5brkxdl13y1i99ih4ia9w6q7h-bcache-tools-1.1', '/nix/store/xr9mx11i6gary2gbxnkfbxrdd0nfi4bx-dbus-1.16.2', '/nix/store/xvd9s1sg5fb4zrvr649i4dydrrkngrj1-zstd-1.5.7-bin', '/nix/store/xzp9smmjljk2a0kk5m4igwflgyxjc9hr-which-2.23-info', '/nix/store/y2lkr8kdhqj39xxmvaffc87dywprggkc-nix-2.34.8-doc', '/nix/store/y4105ipgyc283cq2hx0xknddrfjvfrmn-which-2.23-man', '/nix/store/y51431wmnm7vli4l347dpn44nyhmcrw7-time-1.10', '/nix/store/y5lxyklc4l8z17syin37yzqza3yy2n65-dbus-1.16.2-doc', '/nix/store/yci3pmrwlnppjbl8gnipa1r2hfbagwpw-e2fsprogs-1.47.4-man', '/nix/store/ypdk7h8lfagz3lwbxn454lp0wvn0f0wx-xz-5.8.3-doc', '/nix/store/z6s8nsbr9c38yr6x77xk4j3jbfghiskx-redis-8.8.1', '/nix/store/z8mrhj5yw1imzk2k4dpinl43yqmvnwsn-zstd-1.5.7-man', '/nix/store/z95qf5ykzpj1yifimgnl1fd8phdrzxvd-mkpasswd-5.6.6-man', '/nix/store/zlnq81xi6kb4zvid6sdz2n91wzjd3n70-perl-5.42.0-man', '/nix/store/zp6blqmkgj7kgiydqjnx5imdkqgia9l1-gawk-5.4.1-info', '/nix/store/zwiyw3qsscqrnbpjpd3ji7lsyhybnran-linux-pam-1.7.2-man']}, '/nix/store/9c68h5s7yd50f4f0j5aix2xb3zvh7x27-dbus-1': {'nar_hash': 'sha256-aheuaNYdFcpvxxp+VcCRq9Ek3pb4d1gRbg4hymRqnhU=', 'references': ['/nix/store/g9j71wl28a0c63w58vg3jrpkmpp45fl3-system-path', '/nix/store/xr9mx11i6gary2gbxnkfbxrdd0nfi4bx-dbus-1.16.2']}, '/nix/store/wxl1xfhf0zarzj6sziwafrngqjnzsl6y-X-Restart-Triggers-dbus-broker': {'nar_hash': 'sha256-Z99zMAAROKPw12l0w0e8YTz7Mq0N6O45W8x39S/qgv4=', 'references': ['/nix/store/9c68h5s7yd50f4f0j5aix2xb3zvh7x27-dbus-1']}, '/nix/store/003c65s978q16nmfagyjipkh0jqzh5fd-unit-dbus-broker.service': {'nar_hash': 'sha256-T64TQjbx2U7wbul0PRERTZnAR+pVLuy2ipEvc5SqUsQ=', 'references': ['/nix/store/0xiinbh7pbj479i5v28mqnjrvhvbdibf-systemd-260.2', '/nix/store/41b4nygazaawgbags71flx463x4426kf-glibc-locales-2.42-67', '/nix/store/gph17gb73p6qbrqqjnypfjj5npf0ldyx-coreutils-9.11', '/nix/store/jwq26byp7q4mxqg3yqqq4vgsabs7yknm-findutils-4.10.0', '/nix/store/m2sv1rizzbnsb35hv3ii0dnf3rvfy3n3-tzdata-2026c', '/nix/store/sacz532zgiacvg7mva9v6gbfmyw427i3-gnugrep-3.12', '/nix/store/svl89366pvzz5s3myh1fjniz9l0x17fh-gnused-4.10', '/nix/store/wxl1xfhf0zarzj6sziwafrngqjnzsl6y-X-Restart-Triggers-dbus-broker']}, '/nix/store/jb6zcj0vjg4bagz5x43nzfapdkxvnax7-nftables-deletions': {'nar_hash': 'sha256-CFYxdY2yqARdhk6a4yk+6Gh61UOS4nVFFHrPUQx9oWc=', 'references': []}, '/nix/store/01avmyf870am91qy9dcwgnlqq8ggp6dq-nftables-save-deletions': {'nar_hash': 'sha256-lgh/AMDUsjUipH/2bTcKT+BztsqPS4W9XtjOmBPGC7o=', 'references': ['/nix/store/jb6zcj0vjg4bagz5x43nzfapdkxvnax7-nftables-deletions', '/nix/store/rzl7zd3zx56vl7m55x1l49sr4xx2bb7y-bash-5.3p9']}, '/nix/store/46qp9p9bcr1302szsjmryjjajbkai2ds-mrjam-reviewed-readiness-overlay.json': {'nar_hash': 'sha256-dC3IL864P0pVi0/ZNAXZ7RSr8uxpeskUXX9lDXyamMo=', 'references': []}, '/nix/store/8xghp38id2svx5mr15hnsr3kq5vsxnsx-readiness.patch': {'nar_hash': 'sha256-loHAQXtOr8XuwfJF50MQgQAP/1siVRYbbQxd+yOhf0s=', 'references': []}, '/nix/store/k0v9w3sfd1a8z0q8pnfq6f5kr1d7gc03-ed-1.22.5': {'nar_hash': 'sha256-tdhlUzLqxoEhWsItMFxugjayIygn7weIoJjwL4nGF88=', 'references': ['/nix/store/dphsh3jff8w6n9p3xbfmkia5krqwv52f-glibc-2.42-103']}, '/nix/store/waj0a65a873mqps7nmrkqijcy2h5nkz2-patch-2.8': {'nar_hash': 'sha256-6tx3imNXLQ34hXMqqW7t6YkxmpIJoEtuEtEbeKNLJKQ=', 'references': ['/nix/store/dphsh3jff8w6n9p3xbfmkia5krqwv52f-glibc-2.42-103', '/nix/store/k0v9w3sfd1a8z0q8pnfq6f5kr1d7gc03-ed-1.22.5']}, '/nix/store/dqrkz95azb8947is7y6mjfgc0h418s83-linux-headers-6.18.7': {'nar_hash': 'sha256-xIRkZIiT//hDCWsVyz7RY3rSoCk8nVbP7B5VRa5hs8s=', 'references': []}, '/nix/store/0bxwvycymkb9jxjgn5n4aq0w5gic42cn-glibc-2.42-103-dev': {'nar_hash': 'sha256-Cu3vaX2a/3NnOZgo85GYYXtJ9BCxJiKUnF8xZW980Dk=', 'references': ['/nix/store/dphsh3jff8w6n9p3xbfmkia5krqwv52f-glibc-2.42-103', '/nix/store/dqrkz95azb8947is7y6mjfgc0h418s83-linux-headers-6.18.7', '/nix/store/pf4b257d72pp3ynm834rihif0xk4hlvr-glibc-2.42-103-bin']}, '/nix/store/rxc6g0q5nkjpr2m85ppdkbiabp01c8g0-gmp-6.3.0': {'nar_hash': 'sha256-CdnQOJmDcDPAGkz+jpjiZ5JYCfUh5gz6ZaECSb7O23M=', 'references': ['/nix/store/dphsh3jff8w6n9p3xbfmkia5krqwv52f-glibc-2.42-103', '/nix/store/rxc6g0q5nkjpr2m85ppdkbiabp01c8g0-gmp-6.3.0']}, '/nix/store/jw892rjnjdqv6kxg0slx7ipc9wx41z3a-mpfr-4.2.2': {'nar_hash': 'sha256-I8UMWzX7C9j1QKDQGYGTPe179H+XIsW/yjCYCPNs3i0=', 'references': ['/nix/store/dphsh3jff8w6n9p3xbfmkia5krqwv52f-glibc-2.42-103', '/nix/store/jw892rjnjdqv6kxg0slx7ipc9wx41z3a-mpfr-4.2.2', '/nix/store/rxc6g0q5nkjpr2m85ppdkbiabp01c8g0-gmp-6.3.0']}, '/nix/store/2fsyrjgfff212x1giwf8981adsl3iwhr-libmpc-1.4.0': {'nar_hash': 'sha256-P/97qHGYzqI5olFazcQ2WRmOldykEyZj4QXmdE895mA=', 'references': ['/nix/store/2fsyrjgfff212x1giwf8981adsl3iwhr-libmpc-1.4.0', '/nix/store/dphsh3jff8w6n9p3xbfmkia5krqwv52f-glibc-2.42-103', '/nix/store/jw892rjnjdqv6kxg0slx7ipc9wx41z3a-mpfr-4.2.2', '/nix/store/rxc6g0q5nkjpr2m85ppdkbiabp01c8g0-gmp-6.3.0']}, '/nix/store/68abz6vn5rla742qz1wg1k699pzjy7rh-isl-0.20': {'nar_hash': 'sha256-zl6i94PrTNyEpZNTWVq2eZTYcOVFdYCCE//i+EheaSU=', 'references': ['/nix/store/68abz6vn5rla742qz1wg1k699pzjy7rh-isl-0.20', '/nix/store/dphsh3jff8w6n9p3xbfmkia5krqwv52f-glibc-2.42-103', '/nix/store/rxc6g0q5nkjpr2m85ppdkbiabp01c8g0-gmp-6.3.0']}, '/nix/store/0bchm5z0mbr7agdjg40yj778marg93rw-gcc-15.3.0': {'nar_hash': 'sha256-pDECSVQcMBxFsNoVe558ZIuEOdeSbQKNPA4acXqXYaE=', 'references': ['/nix/store/0ba5kj6r0zhfwd84l5vzccqvx7amlq2c-gcc-15.3.0-lib', '/nix/store/0bchm5z0mbr7agdjg40yj778marg93rw-gcc-15.3.0', '/nix/store/0bxwvycymkb9jxjgn5n4aq0w5gic42cn-glibc-2.42-103-dev', '/nix/store/2fsyrjgfff212x1giwf8981adsl3iwhr-libmpc-1.4.0', '/nix/store/68abz6vn5rla742qz1wg1k699pzjy7rh-isl-0.20', '/nix/store/7b063z98zcilpmzj2sz7sl56gl84zf02-zlib-1.3.2', '/nix/store/dphsh3jff8w6n9p3xbfmkia5krqwv52f-glibc-2.42-103', '/nix/store/jw892rjnjdqv6kxg0slx7ipc9wx41z3a-mpfr-4.2.2', '/nix/store/rxc6g0q5nkjpr2m85ppdkbiabp01c8g0-gmp-6.3.0']}, '/nix/store/6p2dj5zcmj3bi55na180nf68zjqn2n3n-expand-response-params': {'nar_hash': 'sha256-4yiD2enZhtw/9BXhaiLnU5MHXoJEOe9UGrlllRzaXNk=', 'references': ['/nix/store/dphsh3jff8w6n9p3xbfmkia5krqwv52f-glibc-2.42-103']}, '/nix/store/syxzf7s3381x9jcjq2g9sl9n8clcbv4x-binutils-2.46-lib': {'nar_hash': 'sha256-w/j+Jp1rTcYi/VZBCG3qPD7DJAfIs4rSe3D+goC/4XA=', 'references': ['/nix/store/7b063z98zcilpmzj2sz7sl56gl84zf02-zlib-1.3.2', '/nix/store/dphsh3jff8w6n9p3xbfmkia5krqwv52f-glibc-2.42-103', '/nix/store/syxzf7s3381x9jcjq2g9sl9n8clcbv4x-binutils-2.46-lib']}, '/nix/store/3cxvp1557n7hyz4imh2rhkyl64zl7vlw-binutils-2.46': {'nar_hash': 'sha256-VpPDkG8QVVXKXMIcnxJDFaV6aVLGFSpvyX9Sn7nvvyw=', 'references': ['/nix/store/0ba5kj6r0zhfwd84l5vzccqvx7amlq2c-gcc-15.3.0-lib', '/nix/store/3cxvp1557n7hyz4imh2rhkyl64zl7vlw-binutils-2.46', '/nix/store/7b063z98zcilpmzj2sz7sl56gl84zf02-zlib-1.3.2', '/nix/store/dphsh3jff8w6n9p3xbfmkia5krqwv52f-glibc-2.42-103', '/nix/store/syxzf7s3381x9jcjq2g9sl9n8clcbv4x-binutils-2.46-lib']}, '/nix/store/c1a2l64csn5lrwjqqnaman6hdici70vq-binutils-wrapper-2.46': {'nar_hash': 'sha256-k11JWcwQqPtI55j1/M9I01nsL3XpO/q8GHwhck0FGG8=', 'references': ['/nix/store/0bxwvycymkb9jxjgn5n4aq0w5gic42cn-glibc-2.42-103-dev', '/nix/store/3cxvp1557n7hyz4imh2rhkyl64zl7vlw-binutils-2.46', '/nix/store/6p2dj5zcmj3bi55na180nf68zjqn2n3n-expand-response-params', '/nix/store/c1a2l64csn5lrwjqqnaman6hdici70vq-binutils-wrapper-2.46', '/nix/store/dphsh3jff8w6n9p3xbfmkia5krqwv52f-glibc-2.42-103', '/nix/store/hc49zakwkkyp9zlyl80b71jhxkpn4hsx-bash-5.3p9', '/nix/store/kwc34h21my8mf7xbqm9gxs1xfx07xb4i-coreutils-9.11', '/nix/store/pf4b257d72pp3ynm834rihif0xk4hlvr-glibc-2.42-103-bin']}, '/nix/store/0592hadxldzhhd3ppc6nskslzd39fwlz-gcc-wrapper-15.3.0': {'nar_hash': 'sha256-SDluAwLor0JjVuBviuUl8lVfw2NwvbhbHvplEl/0apA=', 'references': ['/nix/store/0592hadxldzhhd3ppc6nskslzd39fwlz-gcc-wrapper-15.3.0', '/nix/store/0ba5kj6r0zhfwd84l5vzccqvx7amlq2c-gcc-15.3.0-lib', '/nix/store/0bchm5z0mbr7agdjg40yj778marg93rw-gcc-15.3.0', '/nix/store/0bxwvycymkb9jxjgn5n4aq0w5gic42cn-glibc-2.42-103-dev', '/nix/store/6p2dj5zcmj3bi55na180nf68zjqn2n3n-expand-response-params', '/nix/store/c1a2l64csn5lrwjqqnaman6hdici70vq-binutils-wrapper-2.46', '/nix/store/dphsh3jff8w6n9p3xbfmkia5krqwv52f-glibc-2.42-103', '/nix/store/hc49zakwkkyp9zlyl80b71jhxkpn4hsx-bash-5.3p9', '/nix/store/kwc34h21my8mf7xbqm9gxs1xfx07xb4i-coreutils-9.11', '/nix/store/pbxald1gihb1bl9l30j764q0ibb55421-gnugrep-3.12', '/nix/store/pf4b257d72pp3ynm834rihif0xk4hlvr-glibc-2.42-103-bin']}, '/nix/store/10psfl320cvkha5m17kmizfwwvvnlrwn-mrjam-elm-validation-cache': {'nar_hash': 'sha256-163G/w3VZOEtP2FrR/CK0rtMXvVjGMwXrN2TB1LPFIo=', 'references': []}, '/nix/store/26qr08ambmn7g5dccqbr8q7aqkvcd92f-check_git_tree.py': {'nar_hash': 'sha256-FkFbvSZ2xmmzOIjF2i4fGXy1ZXSYL9rszWCRnTWT1s0=', 'references': []}}}
CURRENT = '/nix/store/phi68cwg38madbq8p805yvrsyry8g8wr-nixos-system-srv1982677-26.05pre-git'
DIRECTORY = Path('/var/lib/mrjam-deployment-delivery/ci-host-Q-import-001-20261103')
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
