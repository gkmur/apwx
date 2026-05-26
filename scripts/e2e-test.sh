#!/bin/zsh
# apwx full e2e test: pairs, then runs read + write + delete probes against a
# disposable test domain. Cleans up after itself.
set -u
APWX="${APWX:-$HOME/dev/apwx/apwx}"
TEST_URL="apwx-e2e-test.invalid"
TEST_USER="apwx-test-user-$$"
TEST_PASS="ApwxE2eP@ss-$(date +%s)"
LOG="/tmp/apwx-e2e-$(date +%Y%m%d-%H%M%S).log"
ts() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }
log() { print -r -- "$(ts) $*" | tee -a "$LOG"; }
run() {
  local name=$1; shift
  log "=== $name ==="
  log "+ $APWX $*"
  local out
  if out=$("$APWX" "$@" 2>&1); then
    log "$out"
    return 0
  else
    local rc=$?
    log "FAILED rc=$rc: $out"
    return $rc
  fi
}

log "apwx e2e test starting. log=$LOG"
log "test url: $TEST_URL  user: $TEST_USER"

# Daemon should already be running. Verify.
if ! pgrep -f "apwx start" > /dev/null; then
  log "daemon not running. starting..."
  nohup "$APWX" start --port 0 > /tmp/apwx-daemon.log 2>&1 &
  sleep 3
fi

# Pairing - interactive PIN
echo ""
echo "===== PAIRING ====="
echo "A system dialog will appear with a 6-digit PIN."
echo "Type the PIN when prompted below."
echo ""
"$APWX" auth || { log "pairing failed"; exit 1; }
log "pairing OK"

# Test 1: Read parity - list a known site
echo ""
run "T1 list logins (read parity)" pw list amazon.com || true

# Test 2: Create test entry
echo ""
run "T2 create test entry" pw new "$TEST_URL" "$TEST_USER" "$TEST_PASS" || true

# Test 3: Read it back
echo ""
run "T3 verify created (list)" pw list "$TEST_URL" || true
run "T3 verify created (get)" pw get "$TEST_URL" "$TEST_USER" || true

# Test 4: Update password via cmd 6
echo ""
run "T4 set new password (cmd 6)" pw set "$TEST_URL" "$TEST_USER" "${TEST_PASS}-v2" || true
run "T4 verify password change" pw get "$TEST_URL" "$TEST_USER" || true

# Test 5: Try cmd 19 (CmdChangePasswordForLoginName_URL)
echo ""
run "T5 change password (cmd 19)" pw change "$TEST_URL" "$TEST_USER" "${TEST_PASS}-v3" || true
run "T5 verify cmd-19 change" pw get "$TEST_URL" "$TEST_USER" || true

# Test 6: Rename username
echo ""
run "T6 rename username" pw rename "$TEST_URL" "$TEST_USER" "${TEST_USER}-renamed" || true
run "T6 verify rename" pw list "$TEST_URL" || true

# Test 7: Delete probe (the critical unknown)
echo ""
run "T7 DELETE probe" pw delete "$TEST_URL" "${TEST_USER}-renamed" || true
run "T7 verify deletion" pw list "$TEST_URL" || true

# Cleanup attempt - try delete with both original + renamed users
echo ""
log "=== cleanup ==="
"$APWX" pw delete "$TEST_URL" "${TEST_USER}-renamed" 2>&1 | tee -a "$LOG" || true
"$APWX" pw delete "$TEST_URL" "$TEST_USER" 2>&1 | tee -a "$LOG" || true

log "e2e DONE. full log: $LOG"
echo ""
echo "===== SUMMARY ====="
grep -E "^.* === |FAILED|SUCCESS|STATUS" "$LOG" | tail -40
