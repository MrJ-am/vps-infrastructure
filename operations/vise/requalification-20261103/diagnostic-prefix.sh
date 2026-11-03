#!/nix/store/rzl7zd3zx56vl7m55x1l49sr4xx2bb7y-bash-5.3p9/bin/bash
set -e

set -euo pipefail
umask 0077
# No contact, account key, registration or ACME output enters journald.
exec >/dev/null 2>&1
exec 3>/run/mrjam-acme/vise-diagnostic-001.json
trap 'printf "{\"line\":%s,\"exit\":%s}\n" "$LINENO" "$?" >&3' EXIT
exec 9>/run/mrjam-acme/renew.lock
flock -x 9
test -d accounts
test ! -L accounts
test -d certificates
test ! -L certificates
test -d out
test ! -L out
# Select exactly one existing account. A missing/ambiguous account fails
# before network access. Contact stays in this private process environment.
mapfile -d "" account_keys < <(find -P accounts -type f -name '*.key' -print0)
test "${#account_keys[@]}" -eq 1
account_key="${account_keys[0]}"
test -s "$account_key"
test ! -L "$account_key"
export LEGO_EMAIL="${account_key##*/}"
export LEGO_EMAIL="${LEGO_EMAIL%.key}"
test -n "$LEGO_EMAIL"
case "$LEGO_EMAIL" in *$'\n'*|*$'\r'*|*'/'*) exit 1;; esac
# Match lego's exact layout before it can look up a different identity.
account_user="accounts/acme-v02.api.letsencrypt.org/$LEGO_EMAIL"
test "$account_key" = "$account_user/keys/$LEGO_EMAIL.key"
for directory in accounts/acme-v02.api.letsencrypt.org "$account_user" "$account_user/keys"; do
  test -d "$directory"
  test ! -L "$directory"
done
registration="$account_user/account.json"
test -s "$registration"
test ! -L "$registration"
for extension in crt key json issuer.crt; do
  file="certificates/vise.mrj.am.$extension"
  test -s "$file"
  test ! -L "$file"
done
# There is deliberately no lego run/register fallback and no self-signed
# certificate path. Missing state cannot create a new account or cert.
exit 0
