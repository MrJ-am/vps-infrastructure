{ lib, python3, forgejo-runner }:
assert lib.assertMsg (forgejo-runner.version == "13.2.0") "The MRJ.am adapter requires requalification when upstream runner changes.";
forgejo-runner.overrideAttrs (old: {
  pname = "mrjam-forgejo-runner";
  patches = (old.patches or [ ]) ++ [ ./runner-admission.patch ];
  nativeBuildInputs = (old.nativeBuildInputs or [ ]) ++ [ python3 ];
  postPatch = (old.postPatch or "") + ''
    cp ${./runner-admission.go} internal/app/run/mrjam_admission.go
    cp ${./runner-admission_test.go} internal/app/run/mrjam_admission_test.go
    cp ${./independent-validation.yml} internal/app/run/mrjam_workflow.yml
    ${python3}/bin/python3 -I -S -c '
from pathlib import Path
source = Path("internal/app/run/runner.go").read_text()
assert source.count("runErr = mrjamRun(ctx, task, reporter)") == 1
assert "runErr = r.run(ctx, task, reporter)" not in source
'
  '';
  env = (old.env or { }) // { GOMAXPROCS = "2"; };
  ldflags = (old.ldflags or [ ]) ++ [ "-X code.forgejo.org/forgejo/runner/v13/internal/pkg/ver.version=v13.2.0+mrjam-bounded.1" ];
  passthru = (old.passthru or { }) // { admissionProtocol = 1; };
})
