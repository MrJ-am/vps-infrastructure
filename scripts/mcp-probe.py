#!/usr/bin/env python3
"""Inclure Logique déjà publié dans le contrôle collectif de la bascule MCP."""
import argparse
import json
from pathlib import Path
from probe import check, compare
from registry import ROOT, load


def verifier():
    args=argparse.ArgumentParser()
    args.add_argument('--output',type=Path);args.add_argument('--baseline',type=Path)
    options=args.parse_args()
    projets=load(ROOT/'projects.json')
    projets['logique']=json.loads((ROOT/'operations/logique-site.json').read_text())
    bilan=check(projets)
    if options.baseline:compare(json.loads(options.baseline.read_text()),bilan)
    if options.output:options.output.write_text(json.dumps(bilan,indent=2)+'\n')
    print(f'{len(bilan)} contrôles HTTP/TLS réussis, dont Logique.')


if __name__=='__main__':verifier()
