#!/usr/bin/env python3
"""Diagnose only the HTTP namespace adapter using a pinned prior Nix ELF.

This skips compilation and all later stages; it cannot qualify any artifact.
The complete exact pipeline must still run independently to completion.
"""
import qualify_nix_worker

raise SystemExit(qualify_nix_worker.main(diagnostic=True, candidate_diagnostics=True, http_diagnostic=True))
