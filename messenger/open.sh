#!/bin/bash
# open the messenger window for one device (default: this desk's user); a second argument opens a view (calendar)
M="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
R="$(dirname "$M")"
"$M/start.sh"
sleep 2
A=${1:-zenos}
V=${2:-}
case $A in zenos) P=8096;; sato) P=8097;; tanaka) P=8098;; suzuki) P=8099;; esac
T="ZENOS Messages"; [ "$A" != zenos ] && T="ZENOS Messages · $A (demo device)"
I="$R/icons/zenos-messenger.svg"
case $V in calendar) T="ZENOS Calendar"; I="$R/icons/zenos-calendar.svg";; *) V="";; esac
setsid python3 "$M/zenos_webapp.py" "http://127.0.0.1:$P/${V:+#$V}" "$T" "$I" 980x620 >"/tmp/zenos-msgwin-$A.log" 2>&1 < /dev/null &
