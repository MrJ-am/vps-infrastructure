#!/usr/bin/env python3
"""Audit ciblé, sans lire ni afficher les journaux d'accès ou les secrets."""
import argparse
import json
from pathlib import Path
import re
import shlex
import subprocess


def commande(*args):
    return subprocess.run(args, check=True, text=True, capture_output=True).stdout


def configuration_nginx():
    unite = commande('systemctl', 'cat', 'nginx.service')
    lancement = next(l.partition('=')[2] for l in unite.splitlines() if l.startswith('ExecStart='))
    return commande(*shlex.split(lancement), '-T')


def analyser(configuration):
    # Liste positive : ne jamais publier auth_basic_user_file, proxy headers,
    # snippets libres, chemins de secrets ou contenu de fichiers inclus.
    autorise = r'(?:worker_processes|worker_connections|multi_accept|server_name|listen|location|limit_req_zone|limit_conn_zone|limit_req|limit_conn|limit_req_status|limit_conn_status|client_header_timeout|client_body_timeout|send_timeout|keepalive_timeout|proxy_read_timeout|proxy_connect_timeout|client_max_body_size|access_log|error_log|ssl_reject_handshake)'
    return [l.strip() for l in configuration.splitlines()
            if re.match(r'\s*'+autorise+r'\s',l)]


def principal():
    p=argparse.ArgumentParser();p.add_argument('--sortie',type=Path,required=True);args=p.parse_args()
    rapport={'generation':str(Path('/run/current-system').resolve()),
             'nginx':analyser(configuration_nginx()),
             'journaux_nginx_octets':sum(f.stat().st_size for f in Path('/var/log/nginx').glob('*') if f.is_file()),
             'journal_systeme':commande('journalctl','--disk-usage').strip(),
             'syn_cookies':commande('sysctl','-n','net.ipv4.tcp_syncookies').strip()}
    args.sortie.write_text(json.dumps(rapport,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(rapport,ensure_ascii=False,indent=2))


if __name__=='__main__':principal()
