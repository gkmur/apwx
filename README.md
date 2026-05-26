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

## End-to-end cleanup workflow

```bash
# 1. Export Passwords.app to CSV (File -> Export Passwords)
# 2. Generate a cleanup plan from the CSV
python3 scripts/audit.py --csv ~/Downloads/Passwords.csv --out /tmp/plan.json --aggressive

# 3. Dry-run to inspect
apwx batch --plan /tmp/plan.json --dry-run

# 4. Apply for real
apwx batch --plan /tmp/plan.json
```

## E2E test

```bash
scripts/e2e-test.sh
```

Tests pairing, read parity with apw, all 5 write commands, delete probe, and cleanup against a disposable `apwx-e2e-test.invalid` domain. Requires PIN entry during the pairing step (one-time per setup).

## Verification status (current build)

Items verified programmatically without user gesture:
- ✅ TypeScript compiles cleanly (`deno check`)
- ✅ Binary builds (arm64 Mach-O, 77 MB)
- ✅ Daemon starts and binds to ephemeral UDP port
- ✅ Helper binary spawns on demand from manifest
- ✅ Transport round-trip works (pre-auth call returns `Status.INVALID_SESSION` correctly)
- ✅ Auth request command triggers the PIN dialog (helper UI rendered)

Items requiring one-time PIN gesture by user (cryptographic boundary, by design):
- ⏸ Completing the SRP handshake
- ⏸ Authenticated read parity test
- ⏸ Create/Update/Rename/Delete operations against live keychain

Run `scripts/e2e-test.sh` and enter the 6-digit PIN from the dialog to complete e2e verification.

## Caveats

- **Private API**: Apple can change the protocol any macOS release. Protocol verified against macOS 26 (build 25E231) with helper v26.4.
- **Personal use only**: cannot ship a notarized version that bypasses the helper's `allowed_extensions` allowlist. apw spoofs `"Arc"` as `HSTBRSR` (works for personal use).
- **No multi-account support yet**: pairing is per-1Password-account; switching accounts requires `rm ~/.apwx/config.json && apwx auth` again.

## License

GPL-3.0 (inherited from apw).
