#!/bin/bash
# Build the package twice, in two separate places, and compare. A release is signed only when they match
# (and when a builder on another machine gets the same bytes: zenos_release.py manifest --rebuilt NAME=SHA256).
#   VER=0.1.3 packaging/repro-check.sh
set -euo pipefail
SRC="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
VER="${VER:?set VER}"
T="${TMPDIR:-/var/tmp}/zenos-repro.$$"
mkdir -p "$T/a" "$T/b"
OUT="$T/a" VER="$VER" "$SRC/packaging/build-deb.sh" >/dev/null
OUT="$T/b" VER="$VER" "$SRC/packaging/build-deb.sh" >/dev/null
A="$T/a/zenos_${VER}_amd64.deb"; B="$T/b/zenos_${VER}_amd64.deb"
sa=$(sha256sum "$A" | cut -d' ' -f1); sb=$(sha256sum "$B" | cut -d' ' -f1)
echo "first  $sa"; echo "second $sb"
if [ "$sa" = "$sb" ]; then echo "REPRODUCIBLE"; exit 0; fi
echo "NOT REPRODUCIBLE: files that differ:"
mkdir -p "$T/xa" "$T/xb"
dpkg-deb -R "$A" "$T/xa"; dpkg-deb -R "$B" "$T/xb"
diff -rq "$T/xa" "$T/xb" | head -40
exit 1
