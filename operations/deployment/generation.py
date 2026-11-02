"""Exact NixOS profile operations for a sealed release; no executable CLI.

The three generation paths come from the immutable reviewed release, never
command arguments, environment variables or a mutable runtime configuration.
"""
import os
from pathlib import Path
import re
import subprocess

STORE = re.compile(r"/nix/store/[0-9a-df-np-sv-z]{32}-[A-Za-z0-9+._?=-]+\Z")
PROFILE = "/nix/var/nix/profiles/system"
CURRENT = "/run/current-system"


class Refused(RuntimeError):
    pass


class Generations:
    def __init__(self, previous, staged, promoted, nix_env, run=subprocess.run):
        if (len({previous,staged,promoted}) != 3
                or any(not isinstance(p,str) or not STORE.fullmatch(p) for p in (previous,staged,promoted))
                or not isinstance(nix_env,str) or not nix_env.endswith("/bin/nix-env")
                or not STORE.fullmatch(nix_env.removesuffix("/bin/nix-env"))):
            raise Refused("GENERATION_BINDING_REFUSED")
        self.previous,self.staged,self.promoted = previous,staged,promoted
        self.nix_env,self.run = nix_env,run

    def verify_paths(self):
        for root in (self.previous,self.staged,self.promoted):
            if not Path(root).is_dir() or Path(root).is_symlink():
                raise Refused("GENERATION_MISSING")
            for name in ("bin/switch-to-configuration","activate","init","kernel"):
                if not os.access(Path(root)/name,os.R_OK):
                    raise Refused("GENERATION_INCOMPLETE")

    def execute(self, arguments, timeout):
        try:
            result=self.run(arguments,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,timeout=timeout,check=False,
                            env={"LANG":"C","LC_ALL":"C","NIX_PATH":""})
        except (OSError,subprocess.TimeoutExpired):
            raise Refused("GENERATION_OPERATION_REFUSED") from None
        if result.returncode != 0:
            raise Refused("GENERATION_OPERATION_REFUSED")

    def verify_previous(self):
        self.verify_paths()
        if os.path.realpath(CURRENT)!=self.previous or os.path.realpath(PROFILE)!=self.previous:
            raise Refused("PREVIOUS_GENERATION_CHANGED")

    def select_boot(self, target):
        if target not in (self.previous,self.staged,self.promoted):
            raise Refused("GENERATION_TARGET_REFUSED")
        self.execute([self.nix_env,"--profile",PROFILE,"--set",target],120)
        self.execute([target+"/bin/switch-to-configuration","boot"],180)
        if os.path.realpath(PROFILE)!=target:
            raise Refused("BOOT_PROFILE_MISMATCH")

    def activate(self, target):
        if target not in (self.previous,self.staged,self.promoted):
            raise Refused("GENERATION_TARGET_REFUSED")
        self.execute([target+"/bin/switch-to-configuration","test"],180)
        if os.path.realpath(CURRENT)!=target:
            raise Refused("RUNNING_GENERATION_MISMATCH")


if __name__ == "__main__":
    raise SystemExit(64)
