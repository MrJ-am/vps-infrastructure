set -eu
umask 077
install -d -m 700 /var/backup/vise
work=$(mktemp -d /var/backup/vise/.work-XXXXXXXX)
trap 'rm -rf -- "$work"' EXIT
runuser -u postgres -- pg_dump -h /run/postgresql -Fc etp_carnet > "$work/database.dump"
cp /var/lib/etp-carnet/deletions.log "$work/deletions.log"
host_recipient=$(cat /etc/ssh/ssh_host_ed25519_key.pub)
backup="/var/backup/vise/$(date -u +%Y%m%dT%H%M%SZ).tar.age"
tar -cf - -C "$work" database.dump deletions.log | age -r "$VISE_BACKUP_RECIPIENT" -r "$host_recipient" -o "$backup"
# Verify decryption and dump structure before reporting success; no plaintext log.
age -d -i /etc/ssh/ssh_host_ed25519_key "$backup" 2>/dev/null | tar -xOf - database.dump | pg_restore --list >/dev/null
