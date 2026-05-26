# Apple Passwords Native Messaging Protocol — Schema Reference

Reverse-engineered from the official Apple `iCloud Passwords` Firefox extension v3.3.0 (https://addons.mozilla.org/firefox/addon/icloud-passwords/) plus the `PasswordManagerBrowserExtensionHelper` binary at `/System/Cryptexes/App/System/Library/CoreServices/PasswordManagerBrowserExtensionHelper.app`.

## Transport
- Helper binary spawned via Native Messaging manifest at `/Library/Application Support/Mozilla/NativeMessagingHosts/com.apple.passwordmanager.json`
- Wire frame: 4-byte little-endian length prefix + UTF-8 JSON
- apw bridges via UDP4 loopback so a daemon can multiplex CLI clients

## Commands

```
CmdEndOp                          = 0
CmdUnused1                        = 1
CmdChallengePIN                   = 2    // pairing handshake
CmdSetIconNTitle                  = 3
CmdGetLoginNames4URL              = 4    // read: list logins
CmdGetPassword4LoginName          = 5    // read: get password
CmdSetPassword4LoginName_URL      = 6    // write: update / save
CmdNewAccount4URL                 = 7    // write: create
CmdTabEvent                       = 8
CmdPasswordsDisabled              = 9
CmdReloginNeeded                  = 10
CmdLaunchiCP                      = 11
CmdiCPStateChange                 = 12
CmdLaunchPasswordsApp             = 13
CmdHello                          = 14
CmdOneTimeCodeAvailable           = 15
CmdGetOneTimeCodes                = 16   // read: list TOTP
CmdDidFillOneTimeCode             = 17   // read: get TOTP value
CmdSetUpTOTPGenerator             = 18   // write: create TOTP
CmdChangePasswordForLoginName_URL = 19   // write: explicit pw change
CmdOpenURLInSafari                = 1984
```

Note: apw is missing 18 and 19 from its `Command` enum.

## Actions (inside encrypted SDATA)

```
actUnknown      = -1
actDelete       = 0
actUpdate       = 1
actSearch       = 2
actAddNew       = 3
actMaybeAdd     = 4
actGhostSearch  = 5
```

## Message envelope

Every command after pairing is shaped as:

```json
{
  "cmd": <number>,
  "tabId": <number>,
  "frameId": <number>,
  "url": "<optional>",
  "payload": "<JSON string>"
}
```

`payload` is a JSON string containing:

```json
{
  "QID": "<command name, e.g. CmdNewAccount4URL>",
  "SMSG": {
    "TID": "<session username>",
    "SDATA": "<base64 AES-GCM ciphertext of inner JSON>"
  }
}
```

The inner JSON (encrypted as SDATA) carries `ACT` + operation-specific fields.

## Inner-JSON shapes by operation

### Read: list logins for URL (cmd 4)
```json
{"ACT": 5, "URL": "example.com"}
```

### Read: get password (cmd 5)
```json
{"ACT": 2, "URL": "example.com", "USR": "user@example.com"}
```

### Write: create new account (cmd 7) — actMaybeAdd (4) is what the extension uses; actAddNew (3) is the explicit-create action
```json
{
  "ACT": 4,
  "URL": "",  "USR": "",  "PWD": "",
  "NURL": "example.com",
  "NUSR": "user@example.com",
  "NPWD": "TheNewPassword"
}
```

### Write: update password (cmd 6)
```json
{
  "ACT": 4,
  "URL": "",  "USR": "",  "PWD": "",
  "NURL": "example.com",
  "NUSR": "user@example.com",
  "NPWD": "TheNewPassword"
}
```
Same shape as create — helper distinguishes via the cmd number.

### Write: explicit password change (cmd 19)
Likely same payload shape as cmd 6 but uses `ACT: actUpdate (1)`. To be confirmed by testing.

### Delete (cmd 6 with actDelete) — inferred, must confirm
```json
{
  "ACT": 0,
  "URL": "example.com",
  "USR": "user@example.com",
  "PWD": ""
}
```
**Apple's own extension never sends ACT=0 in its source.** The protocol enum includes it (Status.FAILED_TO_DELETE exists, `actDelete = 0` is defined). We have to probe: does the helper accept ACT=0 over cmd 6 (or cmd 7 or cmd 19)? If yes, we have native delete. If it returns FAILED_TO_DELETE / UNKNOWN_ACTION, fallback to the export/reimport workflow.

### Read: list TOTPs (cmd 16)
```json
{"ACT": 5, "TYPE": "oneTimeCodes", "frameURLs": ["https://example.com"]}
```

### Write: setup TOTP generator (cmd 18) — payload shape TBD
Probably accepts something like:
```json
{"ACT": 3, "URL": "example.com", "USR": "user", "SECRET": "<base32 secret>"}
```
Confirm via testing.

## QID values (string command name in payload)

Each cmd has a paired QID string used in the outer JSON. From the extension:
- cmd 4: `"CmdGetLoginNames4URL"`
- cmd 5: `"CmdGetPassword4LoginName"`
- cmd 6: `"CmdSetPassword4LoginName_URL"` or `"CmdChangePasswordForLoginName_URL"` (cmd 19)
- cmd 7: `"CmdNewAccount4URL"`
- cmd 16: `"CmdGetOneTimeCodes"`
- cmd 17: `"CmdDidFillOneTimeCode"`

## Status codes (from server response)

```
SUCCESS              = 0
GENERIC_ERROR        = 1
INVALID_PARAM        = 2
NO_RESULTS           = 3
FAILED_TO_DELETE     = 4
FAILED_TO_UPDATE     = 5
INVALID_MESSAGE_FORMAT = 6
DUPLICATE_ITEM       = 7
UNKNOWN_ACTION       = 8
INVALID_SESSION      = 9
SERVER_ERROR         = 100
```

## Capabilities feature flags (from cmd 14 `CmdHello` response)

The extension reads `g_nativeAppCapabilities` with at least:
- `canSaveAccountWithEmptyUserName`
- `canFillOneTimeCodes`
- `shouldUseBase64`
- `secretSessionVersion`
- `supportsSubURLs`
- `scanForOTPURIs`

## Browser identity required

The helper checks `HSTBRSR` (host browser) in the Hello message against an allowlist. apw spoofs `"Arc"`. Other apparently accepted values from the binary strings: `Chrome`, `Edge`, `Firefox`. Use `Arc` to match apw's working configuration.

## Open questions / risks

1. **Delete via ACT=0** — Apple's extension doesn't ship a delete UI, so we have no reference for delete request shape. Must probe live and likely accept FAILED_TO_DELETE as the worst case.
2. **CmdChangePasswordForLoginName_URL (19) vs CmdSetPassword4LoginName_URL (6)** — both update passwords. Difference unclear; cmd 19 may be the modern path that handles passkey co-existence. Default to cmd 6 first, fall back if NO_RESULTS.
3. **CmdSetUpTOTPGenerator (18)** — payload shape needs confirmation. If we can't figure it out, leave TOTP creation as future work.

## Sources

- Apple Firefox extension XPI: `https://addons.mozilla.org/firefox/downloads/latest/icloud-passwords/latest.xpi` (v3.3.0, 492KB)
- Helper binary: `/System/Cryptexes/App/System/Library/CoreServices/PasswordManagerBrowserExtensionHelper.app/Contents/MacOS/PasswordManagerBrowserExtensionHelper` (Sequoia/26 build 25E231, version 26.4)
- apw source (for SRP + transport patterns): https://github.com/bendews/apw
