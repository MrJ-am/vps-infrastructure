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

RELEASE = {'schema_version': 1, 'export_sha256': 'bb9371878a74a3d0f54e83213f8de0aa9ca98bef8031adec363c57a036e8f0aa', 'export_bytes': 480966336, 'required_free_bytes': 2035674496, 'artifacts': {'/nix/store/zbr55rvh2hqw6a7mwjsk43y5g9qmlnrx-llhttp-9.4.3': {'nar_hash': 'sha256-Qdu3pDqVeYhVt2lkkLtPjzd9QmiwqiQ8K6lddt2dU+Y=', 'references': ['/nix/store/dphsh3jff8w6n9p3xbfmkia5krqwv52f-glibc-2.42-103']}, '/nix/store/x8vjw40svsx50rfpapnnc9clxpprynfm-llhttp-9.4.3-dev': {'nar_hash': 'sha256-sjwkpg6CfhSsPvjzkRxsQ2haskI/MSyr+u2lFL5TVRw=', 'references': ['/nix/store/x8vjw40svsx50rfpapnnc9clxpprynfm-llhttp-9.4.3-dev', '/nix/store/zbr55rvh2hqw6a7mwjsk43y5g9qmlnrx-llhttp-9.4.3']}, '/nix/store/y2s34m9wa7d29acbzpbhvw3d8hxh8bzc-nghttp3-1.15.0-dev': {'nar_hash': 'sha256-Txy8mq2tUttbVX3lgeWbOyvSVDO1qon0M37kJXJbB6Q=', 'references': ['/nix/store/d2vjl55mqymp5pqk9nshrdx89965fcxx-nghttp3-1.15.0', '/nix/store/y2s34m9wa7d29acbzpbhvw3d8hxh8bzc-nghttp3-1.15.0-dev']}, '/nix/store/fx80b11kzb83zwrz7z5av7bsz02gqip1-libev-4.33': {'nar_hash': 'sha256-BpSolNCwW2o8T4IVAO5HuJkbRmv9HagInWHXrO/rIAY=', 'references': ['/nix/store/dphsh3jff8w6n9p3xbfmkia5krqwv52f-glibc-2.42-103', '/nix/store/fx80b11kzb83zwrz7z5av7bsz02gqip1-libev-4.33']}, '/nix/store/qvf742ivj35rgzp9g8kcnjhx9993wvia-c-ares-1.34.9': {'nar_hash': 'sha256-SSRRnzcM0xpjpveti1eiqCRmJDKSQksGv70XoH+NHao=', 'references': ['/nix/store/dphsh3jff8w6n9p3xbfmkia5krqwv52f-glibc-2.42-103', '/nix/store/qvf742ivj35rgzp9g8kcnjhx9993wvia-c-ares-1.34.9']}, '/nix/store/859np4rbi567gdx0k28gxkklq2qahldy-nghttp2-1.69.0': {'nar_hash': 'sha256-KQ60E+kEGxVn3ly6Yjr7w0vGK1yZiNf0wvR1lbTL5GA=', 'references': ['/nix/store/0ba5kj6r0zhfwd84l5vzccqvx7amlq2c-gcc-15.3.0-lib', '/nix/store/dphsh3jff8w6n9p3xbfmkia5krqwv52f-glibc-2.42-103', '/nix/store/fx80b11kzb83zwrz7z5av7bsz02gqip1-libev-4.33', '/nix/store/j1axc9lgzg1gx08z3vmjrwkvyib9a0l5-nghttp2-1.69.0-lib', '/nix/store/q1fgk31hkgl8a7znhmvb0bq8bbcaf64y-openssl-3.6.5', '/nix/store/qvf742ivj35rgzp9g8kcnjhx9993wvia-c-ares-1.34.9']}, '/nix/store/ys0n6cqchpfk8hc7nlwq3p5qpxby4vs2-nghttp2-1.69.0-dev': {'nar_hash': 'sha256-JYr21gRHtBA4HMkCT54F7RCxJ8xeJle4uWIiWI4TfKs=', 'references': ['/nix/store/859np4rbi567gdx0k28gxkklq2qahldy-nghttp2-1.69.0', '/nix/store/j1axc9lgzg1gx08z3vmjrwkvyib9a0l5-nghttp2-1.69.0-lib', '/nix/store/ys0n6cqchpfk8hc7nlwq3p5qpxby4vs2-nghttp2-1.69.0-dev']}, '/nix/store/zv7jk9knz9g176az3rcm8wyxc68nms8a-nodejs-slim-24.22.1': {'nar_hash': 'sha256-7EXVVtlkZ7gI+WHWU4M2M6OwHPpAq84XEDwEufFoygw=', 'references': ['/nix/store/0ba5kj6r0zhfwd84l5vzccqvx7amlq2c-gcc-15.3.0-lib', '/nix/store/124ca9b7djjkzidqdqzd93mcwqvbpidg-ada-3.4.4', '/nix/store/2l6kf3nfwb4k9c5dsdg8k1fs2jr5qikb-brotli-1.2.1-lib', '/nix/store/41xwpwwpg8jxqgar1jf9lww0xkfy9mjc-ngtcp2-1.22.1', '/nix/store/4qqwpd1f34k9505ljggkh07p5a9pllsz-sqlite-3.53.3', '/nix/store/5lqvbgf40v78y7i5d1kcyzz23jky5yqp-simdutf-6.5.0', '/nix/store/7348w7xcmpri6ajymnp136w2hkz1mdwx-zstd-1.5.7', '/nix/store/7b063z98zcilpmzj2sz7sl56gl84zf02-zlib-1.3.2', '/nix/store/87ygcks0lay6r3bxn8sn6m6lpwxz3ywk-ngtcp2-1.22.1-dev', '/nix/store/a3al4xgkxqp4w718d5ai4nhrk4blm6am-simdjson-4.6.4', '/nix/store/acyqmf1mm0r2hq8xv2sckficwp3dg9qb-icu4c-78.3-dev', '/nix/store/ai689c7gfx1ka7fwarc4vc0cm70ahdfp-icu4c-78.3', '/nix/store/d2vjl55mqymp5pqk9nshrdx89965fcxx-nghttp3-1.15.0', '/nix/store/dphsh3jff8w6n9p3xbfmkia5krqwv52f-glibc-2.42-103', '/nix/store/f0lcjigadrvilgw2fprzdd96fw055q0b-openssl-3.6.5-dev', '/nix/store/hmqgi0grd4ckdyj81bbry6kgqkkha9vs-brotli-1.2.1-dev', '/nix/store/i4w1mj6rawirh6m26k8d9hpcjmrgd3pp-zlib-1.3.2-dev', '/nix/store/j1axc9lgzg1gx08z3vmjrwkvyib9a0l5-nghttp2-1.69.0-lib', '/nix/store/kymjrr0lbkbjxzlz0pphdazryyklg754-merve-1.2.2', '/nix/store/nnqg2qvmax2dd36679aplxgs5zn072qv-uvwasi-0.0.23', '/nix/store/pqv9xk93w9pkpj2s5w373nmisr65jm5c-c-ares-1.34.9-dev', '/nix/store/q1fgk31hkgl8a7znhmvb0bq8bbcaf64y-openssl-3.6.5', '/nix/store/qdm1gxkdmb5jdcv72mjql8j9h54j84sn-sqlite-3.53.3-dev', '/nix/store/wcrbb004ci15dp5d3chhk5kzfdbc22g9-libuv-1.52.1', '/nix/store/wzng3jzfjfk4j0i2y4w6crknydhmx588-c-ares-1.34.9', '/nix/store/x735fzw5abldd4sk10lasz1dkayi3bwr-zstd-1.5.7-dev', '/nix/store/x8vjw40svsx50rfpapnnc9clxpprynfm-llhttp-9.4.3-dev', '/nix/store/xnyn6xlh1kk09parg7sgsqcc7sa7hh28-libuv-1.52.1-dev', '/nix/store/y2s34m9wa7d29acbzpbhvw3d8hxh8bzc-nghttp3-1.15.0-dev', '/nix/store/ys0n6cqchpfk8hc7nlwq3p5qpxby4vs2-nghttp2-1.69.0-dev', '/nix/store/zbr55rvh2hqw6a7mwjsk43y5g9qmlnrx-llhttp-9.4.3', '/nix/store/zv7jk9knz9g176az3rcm8wyxc68nms8a-nodejs-slim-24.22.1']}, '/nix/store/ghmsmds9fr37yq40r84q12n2q80bnnh8-nodejs-slim-24.22.1-corepack': {'nar_hash': 'sha256-rupS9RW0iVPd0yZP09emOJF7TlOmGaNVtJlLX2S/XTg=', 'references': ['/nix/store/13czpvp88x852739v5xi04s871pn35b5-bash-interactive-5.3p9', '/nix/store/zv7jk9knz9g176az3rcm8wyxc68nms8a-nodejs-slim-24.22.1']}, '/nix/store/zfq4xfj25ja11vik413zb66bl0ykqlkz-nodejs-slim-24.22.1-npm': {'nar_hash': 'sha256-Fyo1vk173pwq7J/3M2dxjbn6o1zjaPioXdh6CEkSny4=', 'references': ['/nix/store/13czpvp88x852739v5xi04s871pn35b5-bash-interactive-5.3p9', '/nix/store/zv7jk9knz9g176az3rcm8wyxc68nms8a-nodejs-slim-24.22.1']}, '/nix/store/709kghqbswlhrfshjmrh9sn566gjbwdd-nodejs-24.22.1': {'nar_hash': 'sha256-fNPFFaQRq6vDJ+3J1WM9t/UZU2AXMKjFhpVre83v3rk=', 'references': ['/nix/store/ghmsmds9fr37yq40r84q12n2q80bnnh8-nodejs-slim-24.22.1-corepack', '/nix/store/zfq4xfj25ja11vik413zb66bl0ykqlkz-nodejs-slim-24.22.1-npm', '/nix/store/zv7jk9knz9g176az3rcm8wyxc68nms8a-nodejs-slim-24.22.1']}, '/nix/store/y18rr9k4yw3qyrd2ca0p4s5g565wpd92-elm-0.19.1': {'nar_hash': 'sha256-Y4rqvwmgvV9Rht3vP0avsTIPrRb5TMaNH5EB12DZT9k=', 'references': ['/nix/store/4whvlsd07mc0rrkpdinhnhgixrzk7lkv-ncurses-6.6', '/nix/store/709kghqbswlhrfshjmrh9sn566gjbwdd-nodejs-24.22.1', '/nix/store/7b063z98zcilpmzj2sz7sl56gl84zf02-zlib-1.3.2', '/nix/store/c37jpglrjhdp4y3dkq7g5s8qshv43jnj-elfutils-0.194', '/nix/store/dphsh3jff8w6n9p3xbfmkia5krqwv52f-glibc-2.42-103', '/nix/store/hc49zakwkkyp9zlyl80b71jhxkpn4hsx-bash-5.3p9', '/nix/store/iw7ljvmirxgjxpii7zhkxikiaq5vbqz9-gmp-with-cxx-6.3.0', '/nix/store/mhdban9k5rif6n21v9wqnxpbh9kbq647-libffi-3.8.0', '/nix/store/q1fgk31hkgl8a7znhmvb0bq8bbcaf64y-openssl-3.6.5', '/nix/store/wxviinn45m625y2ja34dv8q0b9bxwk0w-numactl-2.0.18', '/nix/store/y18rr9k4yw3qyrd2ca0p4s5g565wpd92-elm-0.19.1']}, '/nix/store/z0gvz1ynawnkvrrlh2c69x3l255jf0rd-mrjam-pinned-build-inputs': {'nar_hash': 'sha256-8pM5Usgk1qk09yA7YoZ0d4h0LOTQvBf7MeONvhcKcb4=', 'references': []}, '/nix/store/z52pmb1ih6bqgc1yparljbx380da4vhk-mrjam-protected-frontend-support': {'nar_hash': 'sha256-lPEZZ/63S0x56oPWlnJ/YwEsG+Gnlj5CGcPjTJyfEQA=', 'references': ['/nix/store/z52pmb1ih6bqgc1yparljbx380da4vhk-mrjam-protected-frontend-support']}, '/nix/store/1hmhhga06lnf0k90j0bm4m5pp6acnm59-postgresql-17.11-man': {'nar_hash': 'sha256-iHi2HLc32CqvlFHYjGBRko8P+lGGqDIPUHNF/kwWmqY=', 'references': []}, '/nix/store/l7qh6kfw0i3i3prf7acq1wd34ax8k8lx-pgvector-0.8.2': {'nar_hash': 'sha256-s/NNNG8Xh7gEXGxqJ4j+K3X7AP+txPb0cCRgP4ESdRQ=', 'references': ['/nix/store/dphsh3jff8w6n9p3xbfmkia5krqwv52f-glibc-2.42-103']}, '/nix/store/zijdg15hs3x3svcqajaagqf8hfgz7qv6-postgresql-and-plugins-17.11': {'nar_hash': 'sha256-dGt9N3RSvgWxxOvhqcOfb34XexAK1b64IRwzLw9cCFM=', 'references': ['/nix/store/0ba5kj6r0zhfwd84l5vzccqvx7amlq2c-gcc-15.3.0-lib', '/nix/store/1hmhhga06lnf0k90j0bm4m5pp6acnm59-postgresql-17.11-man', '/nix/store/dphsh3jff8w6n9p3xbfmkia5krqwv52f-glibc-2.42-103', '/nix/store/hfk2znm53zp4x7hjjh35didm9znjw8jn-postgresql-17.11', '/nix/store/l7qh6kfw0i3i3prf7acq1wd34ax8k8lx-pgvector-0.8.2', '/nix/store/zijdg15hs3x3svcqajaagqf8hfgz7qv6-postgresql-and-plugins-17.11']}, '/nix/store/zx6fpf336icm24bx2cfhc50vs9alvhhr-mrjam-current-validator-runtime-v1.json': {'nar_hash': 'sha256-k/XxROQ7S054s6NLZnKf1u4Jr1Zt3XG6JDh3ZWZtRqM=', 'references': ['/nix/store/0592hadxldzhhd3ppc6nskslzd39fwlz-gcc-wrapper-15.3.0', '/nix/store/10psfl320cvkha5m17kmizfwwvvnlrwn-mrjam-elm-validation-cache', '/nix/store/13czpvp88x852739v5xi04s871pn35b5-bash-interactive-5.3p9', '/nix/store/26qr08ambmn7g5dccqbr8q7aqkvcd92f-check_git_tree.py', '/nix/store/2va2x1g4ncjhaih1dk0zxvi97s832pw9-mrjam-rust-toolchain-1.99.1', '/nix/store/c1a2l64csn5lrwjqqnaman6hdici70vq-binutils-wrapper-2.46', '/nix/store/cdilc0zq2gxyjpgcynnwrgr6hxfv5r38-mrjam-elm-validation-tools', '/nix/store/chk7gc2ii1xmw6srhdh0fq7cjxfpy391-mrjam-current-validator-proposed-policy-v2.json', '/nix/store/f2bsh1n6snqdldnjdshdy1lw3hnlfxwi-bubblewrap-0.12.0', '/nix/store/fya253x5ky7rhfz6rkgdwjr1fzf7fy71-openssl-3.6.5-bin', '/nix/store/h4pqd20idzp9vn5hywrq9kfzmjdzgjsr-mrjam-node-build-tool-24.19.0', '/nix/store/ifpnqj76y16xh8rzxprl0linflgamhdp-mrjam-pinned-browser-resources', '/nix/store/ilc04wmg2xh5jncdbc4v5zc0jdzag4mz-pkg-config-wrapper-0.29.2', '/nix/store/kdnbkivxcszycbn8fqm0hi1d77gfqlnc-mrjam-protected-http-contract', '/nix/store/kp6p38x6zb21n7gdlnp9nsm2aagq7sg2-python3-3.13.17', '/nix/store/kwc34h21my8mf7xbqm9gxs1xfx07xb4i-coreutils-9.11', '/nix/store/l6c4bjcvy4r6yyh2fyj4y7347dxzv6vg-overrides', '/nix/store/q0kvfykalwya20s1ab635ldwbk1r0336-mrjam-verifier-support', '/nix/store/v8izrc2pmwnmfm4ariisf2jh0gf5wpvi-mrjam-canonical-review-rules', '/nix/store/y18rr9k4yw3qyrd2ca0p4s5g565wpd92-elm-0.19.1', '/nix/store/z0gvz1ynawnkvrrlh2c69x3l255jf0rd-mrjam-pinned-build-inputs', '/nix/store/z52pmb1ih6bqgc1yparljbx380da4vhk-mrjam-protected-frontend-support', '/nix/store/zijdg15hs3x3svcqajaagqf8hfgz7qv6-postgresql-and-plugins-17.11']}, '/nix/store/aj0m8465xcx0fzg03lkrvlnbxvldy6zm-mrjam-validate-current-readiness-1': {'nar_hash': 'sha256-ccWYvZ+frJ3wafs7ZSCJpmHqtjbfqSoRvRx43B5nKes=', 'references': ['/nix/store/46qp9p9bcr1302szsjmryjjajbkai2ds-mrjam-reviewed-readiness-overlay.json', '/nix/store/8xghp38id2svx5mr15hnsr3kq5vsxnsx-readiness.patch', '/nix/store/aj0m8465xcx0fzg03lkrvlnbxvldy6zm-mrjam-validate-current-readiness-1', '/nix/store/hc49zakwkkyp9zlyl80b71jhxkpn4hsx-bash-5.3p9', '/nix/store/kp6p38x6zb21n7gdlnp9nsm2aagq7sg2-python3-3.13.17', '/nix/store/waj0a65a873mqps7nmrkqijcy2h5nkz2-patch-2.8', '/nix/store/zx6fpf336icm24bx2cfhc50vs9alvhhr-mrjam-current-validator-runtime-v1.json']}, '/nix/store/k07544vp3n9hfww11na9zq5rm1j8d78y-closure-info': {'nar_hash': 'sha256-5uYTOZarKMJ3/SZ4PZ2mZSYGtgFszHeCz2cwbr3KmC0=', 'references': ['/nix/store/0592hadxldzhhd3ppc6nskslzd39fwlz-gcc-wrapper-15.3.0', '/nix/store/0ba5kj6r0zhfwd84l5vzccqvx7amlq2c-gcc-15.3.0-lib', '/nix/store/0bchm5z0mbr7agdjg40yj778marg93rw-gcc-15.3.0', '/nix/store/0bxwvycymkb9jxjgn5n4aq0w5gic42cn-glibc-2.42-103-dev', '/nix/store/10d0lpvg6pxnzlgnrdpm3xjyki00zgah-gdbm-1.26-lib', '/nix/store/10psfl320cvkha5m17kmizfwwvvnlrwn-mrjam-elm-validation-cache', '/nix/store/124ca9b7djjkzidqdqzd93mcwqvbpidg-ada-3.4.4', '/nix/store/13czpvp88x852739v5xi04s871pn35b5-bash-interactive-5.3p9', '/nix/store/1d733bdg61s0qwwr04xiyrqz4wydv3ym-xz-5.8.4', '/nix/store/1hmhhga06lnf0k90j0bm4m5pp6acnm59-postgresql-17.11-man', '/nix/store/26qr08ambmn7g5dccqbr8q7aqkvcd92f-check_git_tree.py', '/nix/store/2fsyrjgfff212x1giwf8981adsl3iwhr-libmpc-1.4.0', '/nix/store/2l6kf3nfwb4k9c5dsdg8k1fs2jr5qikb-brotli-1.2.1-lib', '/nix/store/2va2x1g4ncjhaih1dk0zxvi97s832pw9-mrjam-rust-toolchain-1.99.1', '/nix/store/31f225xam9v06jnm4878id3ch2wjkgkl-keyutils-1.6.3-lib', '/nix/store/3cxvp1557n7hyz4imh2rhkyl64zl7vlw-binutils-2.46', '/nix/store/3yhivr3h6801yk7sy3skzj4f2j86i68r-readline-8.3p3', '/nix/store/41xwpwwpg8jxqgar1jf9lww0xkfy9mjc-ngtcp2-1.22.1', '/nix/store/46qp9p9bcr1302szsjmryjjajbkai2ds-mrjam-reviewed-readiness-overlay.json', '/nix/store/4fhm41clh7s82xgb3jdnpll1axi9zqgq-xgcc-15.3.0-libgcc', '/nix/store/4k9dyzhafi9dn1qss1aikjrn1flkbvq9-zlib-1.3.2-static', '/nix/store/4qqwpd1f34k9505ljggkh07p5a9pllsz-sqlite-3.53.3', '/nix/store/4whvlsd07mc0rrkpdinhnhgixrzk7lkv-ncurses-6.6', '/nix/store/56vgzbxd1k167sq900dnlp7lldcmznl3-libxml2-2.15.4', '/nix/store/5lqvbgf40v78y7i5d1kcyzz23jky5yqp-simdutf-6.5.0', '/nix/store/68abz6vn5rla742qz1wg1k699pzjy7rh-isl-0.20', '/nix/store/6p2dj5zcmj3bi55na180nf68zjqn2n3n-expand-response-params', '/nix/store/6qr55y5rlrdvm3qy9fpa2pks7xa50yl3-libselinux-3.10', '/nix/store/709kghqbswlhrfshjmrh9sn566gjbwdd-nodejs-24.22.1', '/nix/store/7348w7xcmpri6ajymnp136w2hkz1mdwx-zstd-1.5.7', '/nix/store/7b063z98zcilpmzj2sz7sl56gl84zf02-zlib-1.3.2', '/nix/store/7vbcc5c5fy1ff8hmaca05px0n0l1gj1x-db-4.8.30', '/nix/store/859np4rbi567gdx0k28gxkklq2qahldy-nghttp2-1.69.0', '/nix/store/87ygcks0lay6r3bxn8sn6m6lpwxz3ywk-ngtcp2-1.22.1-dev', '/nix/store/8r9awlc6p0i47vr34p4j11sbgq4mi9bv-mailcap-2.1.54', '/nix/store/8xgfczp5w79qxq7pwxdc15zfmcx2bvxf-postgresql-17.11-lib', '/nix/store/8xghp38id2svx5mr15hnsr3kq5vsxnsx-readiness.patch', '/nix/store/9ldbnd0p3q858l2yznakj63hz3rj10p0-expand-response-params', '/nix/store/9wdq1zinil9w64n9asv6haxyis1php6c-publicsuffix-list-0-unstable-2026-05-13', '/nix/store/a3al4xgkxqp4w718d5ai4nhrk4blm6am-simdjson-4.6.4', '/nix/store/a6d8x05xvrafdg2l8v118sv8jcg25x01-json-c-0.18', '/nix/store/acyqmf1mm0r2hq8xv2sckficwp3dg9qb-icu4c-78.3-dev', '/nix/store/ai689c7gfx1ka7fwarc4vc0cm70ahdfp-icu4c-78.3', '/nix/store/aj0m8465xcx0fzg03lkrvlnbxvldy6zm-mrjam-validate-current-readiness-1', '/nix/store/akmhgr98bcg2nrnls89gl7xz282h1mzf-mpdecimal-4.0.1', '/nix/store/c1a2l64csn5lrwjqqnaman6hdici70vq-binutils-wrapper-2.46', '/nix/store/c37jpglrjhdp4y3dkq7g5s8qshv43jnj-elfutils-0.194', '/nix/store/cdilc0zq2gxyjpgcynnwrgr6hxfv5r38-mrjam-elm-validation-tools', '/nix/store/cg5lp7fwxzib30f6b2lm63p5bd791j6h-acl-2.4.0', '/nix/store/chk7gc2ii1xmw6srhdh0fq7cjxfpy391-mrjam-current-validator-proposed-policy-v2.json', '/nix/store/d2vjl55mqymp5pqk9nshrdx89965fcxx-nghttp3-1.15.0', '/nix/store/d3f8rpj3iy1wx2p2d8fxqab8kdygyi9f-util-linux-minimal-2.42.4-lib', '/nix/store/ddfagd4llkbv8p3cblpa3bxvn6l538yl-systemd-minimal-libs-260.5', '/nix/store/dj6hfwqfynzvy7fp6qc9dwhwxvl71ixd-pcre2-10.49', '/nix/store/dphsh3jff8w6n9p3xbfmkia5krqwv52f-glibc-2.42-103', '/nix/store/dqrkz95azb8947is7y6mjfgc0h418s83-linux-headers-6.18.7', '/nix/store/f0lcjigadrvilgw2fprzdd96fw055q0b-openssl-3.6.5-dev', '/nix/store/f2bsh1n6snqdldnjdshdy1lw3hnlfxwi-bubblewrap-0.12.0', '/nix/store/ffrfb5cybny94sn2gsxxxvg8rqzl2adv-libcap-ng-0.9.3', '/nix/store/fx80b11kzb83zwrz7z5av7bsz02gqip1-libev-4.33', '/nix/store/fya253x5ky7rhfz6rkgdwjr1fzf7fy71-openssl-3.6.5-bin', '/nix/store/ghmsmds9fr37yq40r84q12n2q80bnnh8-nodejs-slim-24.22.1-corepack', '/nix/store/gi9gff3ir00m9j7z801w5fxi9r91axjw-brotli-1.2.1', '/nix/store/h4pqd20idzp9vn5hywrq9kfzmjdzgjsr-mrjam-node-build-tool-24.19.0', '/nix/store/hc49zakwkkyp9zlyl80b71jhxkpn4hsx-bash-5.3p9', '/nix/store/hfk2znm53zp4x7hjjh35didm9znjw8jn-postgresql-17.11', '/nix/store/hl2q8nksy0m8qgh3hzvd24rhill1rpix-libunistring-1.4.2', '/nix/store/hmqgi0grd4ckdyj81bbry6kgqkkha9vs-brotli-1.2.1-dev', '/nix/store/hy66nai3pdjgzhv584c0j6di0y087kdb-krb5-1.22.2-lib', '/nix/store/i4w1mj6rawirh6m26k8d9hpcjmrgd3pp-zlib-1.3.2-dev', '/nix/store/ifpnqj76y16xh8rzxprl0linflgamhdp-mrjam-pinned-browser-resources', '/nix/store/ilc04wmg2xh5jncdbc4v5zc0jdzag4mz-pkg-config-wrapper-0.29.2', '/nix/store/iw7ljvmirxgjxpii7zhkxikiaq5vbqz9-gmp-with-cxx-6.3.0', '/nix/store/j1axc9lgzg1gx08z3vmjrwkvyib9a0l5-nghttp2-1.69.0-lib', '/nix/store/jq0mamb7v8ly6gxyrq8fnrs7al0l3cdp-libssh2-1.11.1', '/nix/store/jw892rjnjdqv6kxg0slx7ipc9wx41z3a-mpfr-4.2.2', '/nix/store/k0qnrn1rz01rvc2ys7vcll4wa80qcrdi-expat-2.9.0', '/nix/store/k0v9w3sfd1a8z0q8pnfq6f5kr1d7gc03-ed-1.22.5', '/nix/store/k41vs2nqfvjqv0k91r0xl5iv0nicv2yl-libxcrypt-4.5.2', '/nix/store/kdnbkivxcszycbn8fqm0hi1d77gfqlnc-mrjam-protected-http-contract', '/nix/store/kp6p38x6zb21n7gdlnp9nsm2aagq7sg2-python3-3.13.17', '/nix/store/kvdgx9r3ssdsnyrvg2wfv6il4pgvazi5-curl-8.23.0', '/nix/store/kwc34h21my8mf7xbqm9gxs1xfx07xb4i-coreutils-9.11', '/nix/store/kymjrr0lbkbjxzlz0pphdazryyklg754-merve-1.2.2', '/nix/store/l6c4bjcvy4r6yyh2fyj4y7347dxzv6vg-overrides', '/nix/store/l7qh6kfw0i3i3prf7acq1wd34ax8k8lx-pgvector-0.8.2', '/nix/store/lrq4wadw7ry4vh0rsnhv7ylshnbld7px-audit-4.2.1-lib', '/nix/store/m07vjyxxxvaly7rzshw0yf18jmpr5bcr-icu4c-76.1', '/nix/store/mhdban9k5rif6n21v9wqnxpbh9kbq647-libffi-3.8.0', '/nix/store/mjxf7qs56s2qyaa309m5634xg73142yc-simdutf-9.0.0', '/nix/store/n56d9xz7m3sc1gvyr2hi9v082abq5sdb-pkg-config-0.29.2', '/nix/store/nnqg2qvmax2dd36679aplxgs5zn072qv-uvwasi-0.0.23', '/nix/store/pbxald1gihb1bl9l30j764q0ibb55421-gnugrep-3.12', '/nix/store/pcxd79slak3wdi1kzkyzzcpcy82sarzs-tzdata-2026e', '/nix/store/pf4b257d72pp3ynm834rihif0xk4hlvr-glibc-2.42-103-bin', '/nix/store/phlf36lhfwaafls84mxvffp8wpz741jn-attr-2.6.0', '/nix/store/pilsssjjdxvdphlg2h19p0bfx5q0jzkn-strip.sh', '/nix/store/pqv9xk93w9pkpj2s5w373nmisr65jm5c-c-ares-1.34.9-dev', '/nix/store/q0kvfykalwya20s1ab635ldwbk1r0336-mrjam-verifier-support', '/nix/store/q1fgk31hkgl8a7znhmvb0bq8bbcaf64y-openssl-3.6.5', '/nix/store/qdm1gxkdmb5jdcv72mjql8j9h54j84sn-sqlite-3.53.3-dev', '/nix/store/qvf742ivj35rgzp9g8kcnjhx9993wvia-c-ares-1.34.9', '/nix/store/rxc6g0q5nkjpr2m85ppdkbiabp01c8g0-gmp-6.3.0', '/nix/store/s45snyx4414z3q1ycj63qh40hqhhs5yr-gmp-with-cxx-6.3.0', '/nix/store/scgsymw7hbvk6hh2cgbdz906iv4v5y9z-libidn2-2.3.8', '/nix/store/syxzf7s3381x9jcjq2g9sl9n8clcbv4x-binutils-2.46-lib', '/nix/store/v3n5aklhc7s1nhj053r6c2lnz7q3nfzy-linux-pam-1.7.2', '/nix/store/v8izrc2pmwnmfm4ariisf2jh0gf5wpvi-mrjam-canonical-review-rules', '/nix/store/waj0a65a873mqps7nmrkqijcy2h5nkz2-patch-2.8', '/nix/store/wcrbb004ci15dp5d3chhk5kzfdbc22g9-libuv-1.52.1', '/nix/store/wkkvmvz3vnbfl3rkf85gp5p5mgp34ak3-gcc-15.3.0-libgcc', '/nix/store/wxviinn45m625y2ja34dv8q0b9bxwk0w-numactl-2.0.18', '/nix/store/wzng3jzfjfk4j0i2y4w6crknydhmx588-c-ares-1.34.9', '/nix/store/x735fzw5abldd4sk10lasz1dkayi3bwr-zstd-1.5.7-dev', '/nix/store/x8ahakmx4pb07rikx4zi25daih9wrsyf-bzip2-1.0.8', '/nix/store/x8vjw40svsx50rfpapnnc9clxpprynfm-llhttp-9.4.3-dev', '/nix/store/xjfr4p44v9hsw80dss844pn1szcaw2ha-libcap-2.77-lib', '/nix/store/xnyn6xlh1kk09parg7sgsqcc7sa7hh28-libuv-1.52.1-dev', '/nix/store/y18rr9k4yw3qyrd2ca0p4s5g565wpd92-elm-0.19.1', '/nix/store/y2s34m9wa7d29acbzpbhvw3d8hxh8bzc-nghttp3-1.15.0-dev', '/nix/store/y3ffb695c582gx3cbd0s2jhs990bkd8z-util-linux-minimal-2.42.4-login', '/nix/store/ybmv0g5xva0wn18zdgxz25bm939lmwlq-lz4-1.10.0-lib', '/nix/store/yishn4jrfiyvh63w7cb1wl01mq4wclag-libpsl-0.21.5', '/nix/store/ys0n6cqchpfk8hc7nlwq3p5qpxby4vs2-nghttp2-1.69.0-dev', '/nix/store/yw17brhraxrgq2wj4j6ibhhincxkz6bc-zstd-1.5.7-bin', '/nix/store/z0gvz1ynawnkvrrlh2c69x3l255jf0rd-mrjam-pinned-build-inputs', '/nix/store/z52pmb1ih6bqgc1yparljbx380da4vhk-mrjam-protected-frontend-support', '/nix/store/zbr55rvh2hqw6a7mwjsk43y5g9qmlnrx-llhttp-9.4.3', '/nix/store/zfq4xfj25ja11vik413zb66bl0ykqlkz-nodejs-slim-24.22.1-npm', '/nix/store/zijdg15hs3x3svcqajaagqf8hfgz7qv6-postgresql-and-plugins-17.11', '/nix/store/zkkfmzdlzwj06fi70qfwx6ky8f8xh670-sqlite-3.53.3-bin', '/nix/store/zv7jk9knz9g176az3rcm8wyxc68nms8a-nodejs-slim-24.22.1', '/nix/store/zx6fpf336icm24bx2cfhc50vs9alvhhr-mrjam-current-validator-runtime-v1.json']}, '/nix/store/040hqydcr6mjpzdrzqfy033lqimx04nh-etc-mrjam-validation-worker-policy.json': {'nar_hash': 'sha256-4InxgefsQ/ZwvEp1mH++caZ77336w1Cq2Iut/wXC9Dk=', 'references': ['/nix/store/aj0m8465xcx0fzg03lkrvlnbxvldy6zm-mrjam-validate-current-readiness-1', '/nix/store/f2bsh1n6snqdldnjdshdy1lw3hnlfxwi-bubblewrap-0.12.0', '/nix/store/k07544vp3n9hfww11na9zq5rm1j8d78y-closure-info']}, '/nix/store/1k7jbm10mxzlxgsz8prnbwfbzywh49xv-unit-mrjam-validation-collector.socket': {'nar_hash': 'sha256-GrSkUDUzcyrCuctkUS8LUOSjLj2tEfZF57m3iPxa6RQ=', 'references': []}, '/nix/store/2k4q8sq2aq92f56vk4w9zxpmxjv14j41-nftables-cleanup-deletions': {'nar_hash': 'sha256-ZZNJSPlZA2xfzCxnRD7g0cIBqFrN5En8lGjObmcjcNk=', 'references': ['/nix/store/rzl7zd3zx56vl7m55x1l49sr4xx2bb7y-bash-5.3p9']}, '/nix/store/3kfgr2ycv49wl7g6g81nvhzbhy6j7wda-unit-mrjam-validation-worker.socket': {'nar_hash': 'sha256-z2czn4pd+48e8QriheanTYhSNyjqBDYak341drloz+w=', 'references': []}, '/nix/store/ngx7v0gbiqp14vcbgd5s9218pdyyf1lh-git-minimal-2.54.0': {'nar_hash': 'sha256-klAHK0/v6a2HoXPH4PgCjPkT6xrfEOXoGLJpZpGzfE0=', 'references': ['/nix/store/0ba5kj6r0zhfwd84l5vzccqvx7amlq2c-gcc-15.3.0-lib', '/nix/store/13czpvp88x852739v5xi04s871pn35b5-bash-interactive-5.3p9', '/nix/store/4k5a466i6n8nvf3fyjkqj8dj1vizcz2i-gettext-1.0', '/nix/store/dphsh3jff8w6n9p3xbfmkia5krqwv52f-glibc-2.42-103', '/nix/store/hc49zakwkkyp9zlyl80b71jhxkpn4hsx-bash-5.3p9', '/nix/store/k0qnrn1rz01rvc2ys7vcll4wa80qcrdi-expat-2.9.0', '/nix/store/kvdgx9r3ssdsnyrvg2wfv6il4pgvazi5-curl-8.23.0', '/nix/store/kwc34h21my8mf7xbqm9gxs1xfx07xb4i-coreutils-9.11', '/nix/store/ngx7v0gbiqp14vcbgd5s9218pdyyf1lh-git-minimal-2.54.0', '/nix/store/pbxald1gihb1bl9l30j764q0ibb55421-gnugrep-3.12', '/nix/store/q1fgk31hkgl8a7znhmvb0bq8bbcaf64y-openssl-3.6.5', '/nix/store/rqpz5lc9g53hda7k5fyzqjvra4cck2fv-gnused-4.10', '/nix/store/vk01x0avwg049mgfwqf5ra31jhycdq8l-zlib-ng-2.3.3']}, '/nix/store/cdj7b2dnn83kbwwhrpia79zbfllxbzsb-mrjam-forgejo-runner-13.2.0': {'nar_hash': 'sha256-lRFr865p1pgGE43d/i5+TngPeklfNtVn6zy07fZL9vM=', 'references': ['/nix/store/8r9awlc6p0i47vr34p4j11sbgq4mi9bv-mailcap-2.1.54', '/nix/store/cdj7b2dnn83kbwwhrpia79zbfllxbzsb-mrjam-forgejo-runner-13.2.0', '/nix/store/ghwcn9lnrczq88sqkcb1ibhwqdchqrp5-iana-etc-20251215', '/nix/store/hc49zakwkkyp9zlyl80b71jhxkpn4hsx-bash-5.3p9', '/nix/store/ngx7v0gbiqp14vcbgd5s9218pdyyf1lh-git-minimal-2.54.0', '/nix/store/pcxd79slak3wdi1kzkyzzcpcy82sarzs-tzdata-2026e']}, '/nix/store/jlff34v3dkfg860sl56rdzhzdvh9km60-bash-interactive-5.3p9-man': {'nar_hash': 'sha256-PMT39dfJSouhOe22vI5y9grFe1pOCF+7Q5kj3qHiZoo=', 'references': []}, '/nix/store/87s5annnji32yjl1wz9c7q1r5xxndab1-mrjam-workflow-client': {'nar_hash': 'sha256-eiuAYWPMmpDbTw1DDZmyF8llF9WMsd9swNxk+bksa10=', 'references': []}, '/nix/store/na6b3i4azc10wr0mczl3wf11d5w5h8hq-mrjam-submit-validation': {'nar_hash': 'sha256-NzAYoHErTu6kwh0a5hHp0fFebrEd365cKyDZzdpISMw=', 'references': ['/nix/store/87s5annnji32yjl1wz9c7q1r5xxndab1-mrjam-workflow-client', '/nix/store/hc49zakwkkyp9zlyl80b71jhxkpn4hsx-bash-5.3p9', '/nix/store/kp6p38x6zb21n7gdlnp9nsm2aagq7sg2-python3-3.13.17']}, '/nix/store/45xxjbxwx5whlgicf5z4dqm14xnfcs51-mrjam-forgejo-coordinator-runtime': {'nar_hash': 'sha256-tz898y0kDM6dOiZtryJNPzEiuC814MxyftUbiWM6+oc=', 'references': ['/nix/store/13czpvp88x852739v5xi04s871pn35b5-bash-interactive-5.3p9', '/nix/store/cdj7b2dnn83kbwwhrpia79zbfllxbzsb-mrjam-forgejo-runner-13.2.0', '/nix/store/jlff34v3dkfg860sl56rdzhzdvh9km60-bash-interactive-5.3p9-man', '/nix/store/kwc34h21my8mf7xbqm9gxs1xfx07xb4i-coreutils-9.11', '/nix/store/na6b3i4azc10wr0mczl3wf11d5w5h8hq-mrjam-submit-validation', '/nix/store/ngx7v0gbiqp14vcbgd5s9218pdyyf1lh-git-minimal-2.54.0']}, '/nix/store/d8bhnl18vsch1zbrvm28w6dvn6acz1k6-mrjam-validation-authority-policy.json': {'nar_hash': 'sha256-Q/DeCsXCFdFSSusUc9KzvCjhBkL8S58x7XmlJJ8Htqk=', 'references': []}, '/nix/store/fdxh1p60i5bdspiqjid5wjv52k9r4scr-mrjam-authority-report-details-v3.json': {'nar_hash': 'sha256-TV7dq4XNLmK6DadJTkxjbSHjjMvpZ3kpWwZJZ8N8/P0=', 'references': []}, '/nix/store/j83qp3j217jl2v5pa5v5zv606pz6ya7k-mrjam-validation-export-policy.json': {'nar_hash': 'sha256-pBwpa1XBiIGkyUiMqsMvQ0wEpQkrKaWcXPL0+C8zaC0=', 'references': []}, '/nix/store/cqz4jlhpis05gj4wcjgaddb45qbfwpz0-mrjam-validation-authority-report-details-3': {'nar_hash': 'sha256-L7nqYGj7HpB0271q5EYVHlz3ndt9mxhXhghCznDkwr0=', 'references': ['/nix/store/cqz4jlhpis05gj4wcjgaddb45qbfwpz0-mrjam-validation-authority-report-details-3', '/nix/store/d8bhnl18vsch1zbrvm28w6dvn6acz1k6-mrjam-validation-authority-policy.json', '/nix/store/fdxh1p60i5bdspiqjid5wjv52k9r4scr-mrjam-authority-report-details-v3.json', '/nix/store/fya253x5ky7rhfz6rkgdwjr1fzf7fy71-openssl-3.6.5-bin', '/nix/store/hc49zakwkkyp9zlyl80b71jhxkpn4hsx-bash-5.3p9', '/nix/store/j83qp3j217jl2v5pa5v5zv606pz6ya7k-mrjam-validation-export-policy.json', '/nix/store/kp6p38x6zb21n7gdlnp9nsm2aagq7sg2-python3-3.13.17']}, '/nix/store/xw72xaazwylp50qf06v7pggr37qx7b03-mrjam-forgejo-runner-content-authority-13.2.0': {'nar_hash': 'sha256-uGbp8iJs5B4aidafX9mJmCz/oy9C751Sj2NObZhpjCE=', 'references': ['/nix/store/8r9awlc6p0i47vr34p4j11sbgq4mi9bv-mailcap-2.1.54', '/nix/store/cqz4jlhpis05gj4wcjgaddb45qbfwpz0-mrjam-validation-authority-report-details-3', '/nix/store/ghwcn9lnrczq88sqkcb1ibhwqdchqrp5-iana-etc-20251215', '/nix/store/hc49zakwkkyp9zlyl80b71jhxkpn4hsx-bash-5.3p9', '/nix/store/ngx7v0gbiqp14vcbgd5s9218pdyyf1lh-git-minimal-2.54.0', '/nix/store/pcxd79slak3wdi1kzkyzzcpcy82sarzs-tzdata-2026e', '/nix/store/xw72xaazwylp50qf06v7pggr37qx7b03-mrjam-forgejo-runner-content-authority-13.2.0']}}}
CURRENT = '/nix/store/phi68cwg38madbq8p805yvrsyry8g8wr-nixos-system-srv1982677-26.05pre-git'
DIRECTORY = Path('/var/lib/mrjam-deployment-delivery/ci-host-Q-import-003-20261103')
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
