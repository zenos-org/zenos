#!/bin/bash
# open the messenger window for one device (default: this desk's user)
M="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
R="$(dirname "$M")"
"$M/start.sh"
sleep 2
A=${1:-zenos}
case $A in zenos) P=8096;; sato) P=8097;; tanaka) P=8098;; suzuki) P=8099;; esac
T="ZENOS Messages"; [ "$A" != zenos ] && T="ZENOS Messages · $A (demo device)"
setsid python3 "$M/zenos_webapp.py" http://127.0.0.1:$P/ "$T" "$R/icons/zenos-messenger.svg" 980x620 >"/tmp/zenos-msgwin-$A.log" 2>&1 < /dev/null &
