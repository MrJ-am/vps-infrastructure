The independent synthetic VM passes all eight groups in `mail-result-001.json`
with the unchanged native worker ELF and the v2 mail adopters. It imports the
actual `state-adoption.nix`, archive, cycle and PostgreSQL peer modules. The
receipt binds their hashes. No VPS, real account, SMTP delivery or remote archive
was used; the guest has no network interface, only loopback.

Run from the repository root:

```sh
nix-build operations/identity/mail-native-systemd.nix \
  --arg nixpkgs /nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source \
  --max-jobs 1 --cores 2 --no-out-link
```

The original sources use the fixed historical locations with UID/GID 984 and
mode 0600. After the test establishes stopped writers, the exact deployment
`stage_adoption.prepare()` creates private SQLite images; its six tests also
exercise committed WAL and ignored uncommitted writes. The three actual systemd
units mount those images read-only and run as their dedicated users. Admission
uses an empty invented schema; the separate worker VM covers populated admission.

The mail tests preserve every MIME byte, retry field, historical proof, nullable
marker and marker-table presence. Duplicate identical messages merge, while a
changed marker or differing message refuses publication without changing the
existing inode or bytes. The 29 adopter tests also run inside the guest.

Both unchanged workers drain old opaque messages. A deliberate STARTTLS refusal
preserves them and increases retry state. Explicitly simulated receipt state is
then preserved without creating or acknowledging SQL erasure intentions from an
old key or marker. An unrelated account remains present. This is a preservation
and safe-resumption proof, not reconciliation of unfinished production erasures.

The archive uses its new private `LoadCredential` configuration for both commands.
Its initializer is idempotent: on adopted state it succeeds without changing the
inode or whole-file digest. The first test incorrectly expected refusal; the
original failure and correction are retained in `mail-initial-findings.json`.
No candidate change was needed. Private values are absent from worker diagnostics,
and the recipient is absent from the unit declaration. Every tested unit is
explicitly stopped at the end.

Passing output: `/nix/store/7j3jhmplfhfxhlfac6ai42rlps4s3496-vm-test-run-mrjam-native-mail-independent`.
This local receipt has no protected governance authority and is not production readiness.
