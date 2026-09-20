#!/bin/sh
set -eu

cd -- "$(dirname -- "$0")"

if command -v sbcl >/dev/null 2>&1; then
  exec sbcl --noinform --non-interactive \
    --eval '(require :asdf)' \
    --eval '(asdf:load-asd (truename "vision.asd"))' \
    --eval '(asdf:load-system :vision)' \
    --eval '(sb-ext:save-lisp-and-die "vision" :toplevel (function vision:main) :executable t)'
fi

if command -v ros >/dev/null 2>&1; then
  exec ros lisp=sbcl-bin/2.3.9 -Q \
    -e '(require :asdf)' \
    -e '(asdf:load-asd (truename "vision.asd"))' \
    -e '(asdf:load-system :vision)' \
    -e '(sb-ext:save-lisp-and-die "vision" :toplevel (function vision:main) :executable t)'
fi

echo 'SBCL or Roswell is required.' >&2
exit 1

