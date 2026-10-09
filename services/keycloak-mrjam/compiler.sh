#!/bin/sh
set -eu
source_mrjam=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
librairies=$1
sortie=$2
atelier_mrjam=$(mktemp -d)
trap 'rm -rf "$atelier_mrjam"' EXIT INT TERM
find "$source_mrjam/src" -name '*.java' -print > "$atelier_mrjam/sources"
javac --release 21 -encoding UTF-8 -cp "$librairies/*" -d "$atelier_mrjam/classes" @"$atelier_mrjam/sources"
cp -R "$source_mrjam/resources/." "$atelier_mrjam/classes/"
# Les ressources du store Nix ont des répertoires en lecture seule. La copie
# temporaire doit être effaçable par nixbld, sans toucher à la source du store.
chmod -R u+w "$atelier_mrjam/classes"
jar --create --file "$sortie" -C "$atelier_mrjam/classes" .
