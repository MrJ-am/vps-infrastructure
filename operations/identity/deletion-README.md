The received server ELF can execute scoped Vision account deletion with the
current native broker and archive/replay workers, without rebuilding any binary.
All eight synthetic groups pass in `deletion-result-001.json`. The received server
SHA-256 remains `f896cd1c17cc85d331474622747f4c019258a1023dfb5963125b235f4a6236cd`.

The same ELF **still rejects** `vision-account-deletion` in
`required_capabilities`, with `REQUIRED_CAPABILITY_MISSING`. This independent
negative test passes before and after the functional test. The positive fixture
declares only `static-assets`; it explicitly configures Vision and its journal
but makes no complete Vision readiness claim. No flag, source or binary was
changed to hide this limitation. There is no JSON setting that makes this
hard-coded capability true; changing that declaration requires a separately
qualified server change. The local proof also does not establish actual external
archive delivery or retention.

Run from the repository root:

```sh
nix-build operations/identity/deletion-native-systemd.nix \
  --arg nixpkgs /nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source \
  --max-jobs 1 --cores 2 --no-out-link
```

The isolated guest uses real Kanidm 1.11.2, real OAuth authorization code exchange,
the current session broker, the received server and actual service modules. No
network interface exists; TLS, PostgreSQL and HTTP use only local invented state.

`POST /api/web/effacer_compte` requires the actual browser session, correct Origin
and CSRF, and exactly `{"confirmation":"EFFACER VISION"}`. The fixture verifies
refusal of missing authentication, wrong Origin/CSRF/host, wrong confirmation and
a caller-supplied owner. Valid repeated requests return HTTP202, create one
durable journal intention and leave content unchanged across a server restart.

The actual archive worker produces an age-encrypted record with the expected
owner. A deliberate SMTP STARTTLS refusal cannot acknowledge that record. The
test then explicitly simulates receipt in the invented outbox; the unchanged
archiver must itself bind the matching SQL receipt. Only afterward does the HTTP
route return HTTP200 with `efface=true`. The requesting Vision account, identity
mapping, profile and private sheet disappear. An unrelated account and the
common native identity remain. Subsequent access is HTTP403 because the Vision
principal is absent. Real replay records the exact archive digest and is
idempotent. This is Vision deletion, not common Log identity closure; the latter
is covered separately in `workers-result-001.json`.

The final receipt also contains only boolean observations of a real service
token's `/v1/self`: HTTP200, `youare.attrs`, exact service name match, class
`service_account`, one lowercase UUID and `memberof` as group SPNs. No token,
claim value, mail address or UUID appears in that evidence.

Two original fixture failures remain in `deletion-initial-findings.json`: an
`/etc` symlink was rightly refused before configuration validation, and the test
initially expected HTTP401 instead of the contract's HTTP403 after deletion.
Both were corrected without changing candidate code. All tested services are
stopped at the end; private markers and credentials are absent from their logs.

Passing output: `/nix/store/z2fr5kfxjmk33qr87liymy753v9xfqrb-vm-test-run-mrjam-existing-server-native-deletion`.
This local evidence has no protected governance authority and is not production readiness.
