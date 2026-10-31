#!/usr/bin/env python3
"""Public-source/synthetic-data diagnostic; never produces qualified artifacts.

Exposes candidate compilation/test output only in this explicit local fixture.
The immutable qualified closure and production worker remain unchanged.
"""
import qualify_nix_worker

raise SystemExit(qualify_nix_worker.main(diagnostic=True, candidate_diagnostics=True))
