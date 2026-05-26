#!/bin/zsh
# apwx setup: launches the daemon (must run on the machine where Apple Passwords lives)
set -u
APWX="${APWX:-$HOME/dev/apwx/apwx}"
if [[ ! -x "$APWX" ]]; then
  echo "apwx binary not found at $APWX. Set APWX env var."
  exit 1
fi
echo "Starting apwx daemon in background..."
nohup "$APWX" start --port 0 > /tmp/apwx-daemon.log 2>&1 &
DAEMON_PID=$!
echo "daemon pid=$DAEMON_PID. log: /tmp/apwx-daemon.log"
sleep 2
echo ""
echo "Now run:  $APWX auth"
echo "1Password.app will display a 6-digit PIN. Enter it when prompted."
echo ""
echo "To stop daemon later: kill $DAEMON_PID"
echo "$DAEMON_PID" > /tmp/apwx-daemon.pid
