#!/bin/sh
set -eu

cd -- "$(dirname -- "$0")/.."

: "${PGHOST:=/run/postgresql}"
: "${PGDATABASE:=vision}"
: "${PGUSER:=vision}"
export PGHOST PGDATABASE PGUSER

for migration in migrations/*.sql; do
  psql --no-psqlrc --set=ON_ERROR_STOP=1 --file="$migration"
done

