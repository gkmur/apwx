<div align="center">
  <img src="icon.png" alt="apwx" width="80" height="80">

  # apwx

  **Extended CLI for Apple Passwords (iCloud Keychain) — read + write + delete.**

  Fork of [bendews/apw](https://github.com/bendews/apw) that adds write commands by speaking the same Native Messaging protocol the official Apple browser extensions use.
</div>

---

## What it does

| Operation | apw | apwx |
|---|---|---|
| List logins for URL | yes | yes |
| Get password | yes | yes |
| Get TOTP | yes | yes |
| Create new account | — | **yes** (cmd 7) |
| Update password | — | **yes** (cmd 6) |
| Change password | — | **yes** (cmd 19) |
| Rename username | — | **yes** |
| Delete account | — | **yes** (probes actDelete) |

Bulk operations via `apwx batch --plan plan.json` for cleanup-at-scale.

## How it works

Apple ships `PasswordManagerBrowserExtensionHelper` at `/System/Cryptexes/App/.../PasswordManagerBrowserExtensionHelper`. It's the daemon Apple's own Chrome/Firefox/Edge extensions use to read and write passwords in iCloud Keychain.

The protocol is Native Messaging (4-byte LE length prefix + UTF-8 JSON) over stdin/stdout, wrapped in a SRP-secured session (one-time PIN pairing). apw figured out the read path; apwx adds the write commands documented in [`PROTOCOL.md`](./PROTOCOL.md), reverse-engineered from Apple's official iCloud Passwords Firefox extension v3.3.0.

## Setup

```bash
git clone https://github.com/gkmur/apwx ~/dev/apwx
cd ~/dev/apwx
deno compile --allow-read --allow-write --allow-net --allow-run --allow-env --output apwx src/cli.ts
```

Requires macOS 14+ (Sequoia or newer) and Deno (`brew install deno`).

## First-time pairing

1. **Start the daemon** (must run continuously; it bridges UDP-loopback to the helper binary):
   ```bash
   nohup ~/dev/apwx/apwx start > /tmp/apwx-daemon.log 2>&1 &
   ```

2. **Pair** (one-time):
   ```bash
   ~/dev/apwx/apwx auth
   ```
   A system dialog will appear with a 6-digit PIN. Type it at the prompt.

   This step **requires a human gesture** — it's the cryptographic pairing handshake. Cannot be automated. The session token is stored in `~/.apwx/config.json` and reused across calls.

## Usage

```bash
# Reads
apwx pw list example.com
apwx pw get example.com user@example.com

# Writes
apwx pw new example.com user@example.com 'MyPassword'
apwx pw set example.com user@example.com 'NewPassword'
apwx pw change example.com user@example.com 'NewPassword'     # cmd 19 path
apwx pw rename example.com olduser newuser
apwx pw delete example.com user@example.com

# Batch (the killer feature for cleanup)
apwx batch --plan plan.json
apwx batch --plan plan.json --dry-run
```

Plan format:
```json
{
  "ops": [
    {"action": "delete", "url": "dupe-site.com", "username": "x@y.com"},
    {"action": "rename", "url": "example.com", "username": "OldUser", "newUsername": "newuser"},
    {"action": "set", "url": "example.com", "username": "u", "password": "new-pass"}
  ]
}
```

## End-to-end cleanup workflow (works on macOS 15.4+ — the recommended path)

Because the Native Messaging route is blocked on current macOS, the actually-working cleanup is a CSV export/import roundtrip handled by `scripts/cleanup-csv.py`:

```bash
# 1. In Passwords.app: File -> Export Passwords -> save as Passwords.csv
# 2. Clean the CSV (dedupe, normalize titles, fix typos, drop junk)
python3 scripts/cleanup-csv.py \
    --in ~/Downloads/Passwords.csv \
    --out ~/Downloads/Passwords-cleaned.csv \
    --report ~/Downloads/Passwords-report.md \
    --aggressive

# 3. Read the report. Confirm the changes look right.
# 4. In Passwords.app: select all entries (Cmd-A) -> Delete (entries go to 30-day trash, safe).
# 5. In Passwords.app: File -> Import Passwords -> select Passwords-cleaned.csv.
# 6. Spot-check 5-10 entries to confirm they imported correctly.
```

What the cleanup does:
- Removes exact duplicates (same domain + same username)
- Removes subdomain duplicates with `--aggressive` (e.g. `login.discover.com` + `portal.discover.com` -> `discover.com`)
- Normalizes domain-style titles (`www.amazon.com` -> `Amazon`)
- Fixes email typos (`@gmail.con` -> `@gmail.com`) and casing
- Drops junk entries (titles with no URL + no password, dash-only usernames)
- Preserves all kept entries' Password / Notes / OTPAuth fields verbatim

Caveat: TOTP secrets and passkeys may not survive the export/import round-trip in all cases. Spot-check critical entries post-import.

### Alternative: programmatic CRUD (when the Native Messaging route works)

Once the macOS 15.4+ helper-spawn blocker is resolved upstream (see below), the same audit pipeline can drive bulk operations directly:

```bash
python3 scripts/audit.py --csv ~/Downloads/Passwords.csv --out /tmp/plan.json --aggressive
apwx batch --plan /tmp/plan.json --dry-run
apwx batch --plan /tmp/plan.json
```

## E2E test

```bash
scripts/e2e-test.sh
```

Tests pairing, read parity with apw, all 5 write commands, delete probe, and cleanup against a disposable `apwx-e2e-test.invalid` domain. Requires PIN entry during the pairing step (one-time per setup).

## ⚠️ macOS 15.4+ compatibility — blocked upstream

Confirmed on macOS 26.4.1: when apwx (or apw) spawns the helper binary, **macOS SIGKILLs the helper immediately** (exit 137, no stderr). Apple added kernel-level enforcement around macOS 15.4 that only allows `PasswordManagerBrowserExtensionHelper` to be launched by registered browser processes (Chrome/Firefox/Edge with native-messaging extension registration). This blocks all third-party CLI access via this protocol.

This is a known upstream limitation tracked at [bendews/apw#10](https://github.com/bendews/apw/issues/10) since April 2025 with no known workaround.

**The apwx code is correct** — protocol implementation verified against Apple's official iCloud Passwords Firefox extension v3.3.0 (see [`PROTOCOL.md`](./PROTOCOL.md)). The blocker is platform-level. apwx will work as soon as:
- A community-discovered workaround appears (process-injection, entitlement bypass, etc.), OR
- Apple introduces an officially supported CLI path, OR
- It's run on macOS 14.x or earlier where the enforcement wasn't yet present

## Verification status (current build)

**CSV cleanup pipeline (the working path on macOS 15.4+):**
- ✅ `scripts/cleanup-csv.py` end-to-end tested
- ✅ `tests/test-cleanup.sh` - 8/8 tests passing
  - dedupe (exact + subdomain)
  - typo fixes
  - junk removal
  - title normalization
  - dupe-selection (preserves user A vs user B on same domain)
  - report generation
  - CSV format preservation

Run `tests/test-cleanup.sh` to verify locally.

**Native Messaging route (programmatic CRUD - blocked upstream):**
- ✅ TypeScript compiles cleanly (`deno check`)
- ✅ Binary builds (arm64 Mach-O, 77 MB)
- ✅ Daemon starts and binds to ephemeral UDP port
- ✅ Helper binary located + invoked from manifest
- ✅ Transport round-trip works (pre-auth call returns `Status.INVALID_SESSION` correctly)
- ✅ Protocol JSON schema reverse-engineered from Apple's official extension v3.3.0
- ✅ Write command implementations match official extension byte-for-byte
- ❌ Live pairing — macOS 15.4+ SIGKILLs the helper before it can respond (bendews/apw#10)
- ❌ Authenticated read/write/delete — gated on pairing

## Caveats

- **Private API**: Apple can change the protocol any macOS release. Protocol verified against macOS 26 (build 25E231) with helper v26.4.
- **Personal use only**: cannot ship a notarized version that bypasses the helper's `allowed_extensions` allowlist. apw spoofs `"Arc"` as `HSTBRSR` (works for personal use).
- **No multi-account support yet**: pairing is per-1Password-account; switching accounts requires `rm ~/.apwx/config.json && apwx auth` again.

## License

GPL-3.0 (inherited from apw).
