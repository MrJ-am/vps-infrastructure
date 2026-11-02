#!/usr/bin/env python3
"""Fixed lstat-only adoption references: no content, size, date or listing."""
import json
import os
import stat
import sys

PATHS = ('/run/mrjam-kanidm-backup', '/run/mrjam-kanidm-backup/kanidm.json.gz', '/var/backup', '/var/backup/forgejo', '/var/backup/mrjam', '/var/backup/mrjam/native-v1', '/var/backup/nextcloud', '/var/backup/postgresql', '/var/lib/forgejo', '/var/lib/forgejo-identity', '/var/lib/forgejo-identity/client.json', '/var/lib/forgejo/.identity-config', '/var/lib/forgejo/.identity-config/app.ini', '/var/lib/forgejo/custom/conf', '/var/lib/forgejo/custom/conf/internal_token', '/var/lib/forgejo/custom/conf/oauth2_jwt_secret', '/var/lib/forgejo/custom/conf/secret_key', '/var/lib/forgejo/repositories', '/var/lib/mrjam-identite', '/var/lib/mrjam-identite/cycle.json', '/var/lib/mrjam-identite/fermeture-hook.secret', '/var/lib/mrjam-identite/kanidm-admission.token', '/var/lib/mrjam-identite/kanidm-cycle.token', '/var/lib/mrjam-identite/kanidm-replay.token', '/var/lib/mrjam-identite/kanidm-vision.secret', '/var/lib/mrjam-identite/proton-smtp.json', '/var/lib/mrjam-worker-credentials', '/var/lib/mrjam-worker-credentials/v1', '/var/lib/mrjam-worker-credentials/v1/approval', '/var/lib/mrjam-worker-credentials/v1/archive-initialize.json', '/var/lib/mrjam-worker-credentials/v1/archive.json', '/var/lib/mrjam-worker-credentials/v1/closure', '/var/lib/mrjam-worker-credentials/v1/recipient', '/var/lib/mrjam-worker-credentials/v1/smtp.json', '/var/lib/nextcloud-php-security', '/var/lib/nextcloud-php-security/blocked', '/var/lib/nextcloud/config', '/var/lib/nextcloud/config/config.php', '/var/lib/nextcloud/data')


def metadata(path):
    try:
        item=os.lstat(path)
        kind='file' if stat.S_ISREG(item.st_mode) else 'directory' if stat.S_ISDIR(item.st_mode) else 'symlink' if stat.S_ISLNK(item.st_mode) else 'special'
        return {'state':'observed','kind':kind,'uid':item.st_uid,'gid':item.st_gid,'mode':stat.S_IMODE(item.st_mode)}
    except FileNotFoundError:
        return {'state':'absent'}
    except Exception:
        return {'state':'unknown'}


def main():
    if len(sys.argv)!=1 or os.geteuid()!=0:
        return 64
    print(json.dumps({'schema_version':1,'scope':'fixed-lstat-only','paths':{p:metadata(p) for p in PATHS},'contents_read':False,'activation_performed':False},sort_keys=True,separators=(',',':')))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
