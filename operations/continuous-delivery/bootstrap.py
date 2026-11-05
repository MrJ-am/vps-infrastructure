#!/usr/bin/env python3
"""Stable system service entrypoint; its engine follows the activated generation."""
import os
from pathlib import Path
import sys

engine = Path('/etc/mrjam-ci/engine').resolve(strict=True)
if not str(engine).startswith('/nix/store/'):
    raise RuntimeError('Expected an immutable delivery engine')
script = 'ci.py' if sys.argv[1] == 'ci' else 'deploy.py'
os.execv(sys.executable, [sys.executable, str(engine / 'operations/continuous-delivery' / script), *sys.argv[2:]])
