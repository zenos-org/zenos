#!/bin/bash
# start the relay and the demo devices if they are not running
M="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
mkdir -p "$HOME/.local/share/zenos/msg"
cd "$HOME/.local/share/zenos/msg"
pgrep -f "node $M/relay.js" >/dev/null || setsid /usr/bin/node $M/relay.js >/tmp/zenos-relay.log 2>&1 < /dev/null &
sleep 1
P=8096
for a in zenos sato tanaka suzuki; do
  pgrep -f "node $M/client.js $a " >/dev/null || setsid /usr/bin/node $M/client.js $a $P >/tmp/zenos-msg-$a.log 2>&1 < /dev/null &
  P=$((P+1))
done
