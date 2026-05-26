#!/usr/bin/env python3
"""
apwx audit: read a Passwords.app CSV export (or apwx pw list dumps) and emit a
plan.json of cleanup operations (renames, deletes for dupes, etc.).

Usage:
  python3 audit.py --csv ~/Downloads/passwords.csv --out plan.json
  python3 audit.py --csv ~/Downloads/passwords.csv --out plan.json --aggressive

CSV expected columns (Passwords.app export):
  Title, URL, Username, Password, Notes, OTPAuth
"""
import argparse, csv, json, re, sys
from collections import defaultdict
from urllib.parse import urlparse


def domain_of(url: str) -> str:
    if not url:
        return ""
    try:
        d = urlparse(url if "://" in url else f"https://{url}").netloc.lower()
        return re.sub(r"^www\.", "", d)
    except Exception:
        return url.lower()


def root_domain(d: str) -> str:
    parts = d.split(".")
    if len(parts) >= 3 and len(parts[-2]) <= 3 and len(parts[-1]) <= 3:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:]) if len(parts) >= 2 else d


def normalize_user(u: str) -> str:
    u = u.strip()
    # Fix gmail.con etc
    if "@" in u and u.lower().endswith(".con"):
        u = u[:-4] + ".com"
    return u


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--aggressive", action="store_true",
                    help="dedupe subdomain variants of the same root domain")
    args = ap.parse_args()

    entries = []
    with open(args.csv) as f:
        reader = csv.DictReader(f)
        for row in reader:
            entries.append({
                "title": (row.get("Title") or "").strip(),
                "url": (row.get("URL") or "").strip(),
                "user": normalize_user(row.get("Username") or ""),
                "password": row.get("Password") or "",
                "notes": row.get("Notes") or "",
                "otp": row.get("OTPAuth") or "",
            })
    print(f"loaded {len(entries)} entries", file=sys.stderr)

    ops = []

    # 1. Username typo/casing fixes - re-read raw CSV to compare against normalized
    with open(args.csv) as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            raw = (row.get("Username") or "").strip()
            fix = normalize_user(raw)
            if raw and raw != fix:
                e = entries[i]
                ops.append({
                    "action": "rename",
                    "url": domain_of(e["url"]),
                    "username": raw,
                    "newUsername": fix,
                    "_reason": "typo/casing fix",
                })

    # 2. Dupe detection (same domain + same username)
    groups = defaultdict(list)
    for e in entries:
        key = (domain_of(e["url"]), e["user"].lower())
        if key[0]:
            groups[key].append(e)

    for key, group in groups.items():
        if len(group) > 1:
            # keep first; archive/delete the rest
            winner = group[0]
            for loser in group[1:]:
                ops.append({
                    "action": "delete",
                    "url": domain_of(loser["url"]),
                    "username": loser["user"],
                    "_reason": f"dupe of {winner['url']} {winner['user']}",
                })

    # 3. Aggressive dedupe: subdomain variants of same root domain + same user
    if args.aggressive:
        seen_root = defaultdict(list)
        for e in entries:
            d = domain_of(e["url"])
            if not d:
                continue
            seen_root[(root_domain(d), e["user"].lower())].append(e)
        for key, group in seen_root.items():
            if len(group) > 1:
                # pick the shortest domain (most likely the root)
                group_sorted = sorted(group, key=lambda x: len(domain_of(x["url"])))
                winner = group_sorted[0]
                for loser in group_sorted[1:]:
                    same_full = (
                        domain_of(loser["url"]) == domain_of(winner["url"])
                        and loser["user"].lower() == winner["user"].lower()
                    )
                    if same_full:
                        continue  # already handled in step 2
                    ops.append({
                        "action": "delete",
                        "url": domain_of(loser["url"]),
                        "username": loser["user"],
                        "_reason": f"subdomain dupe of root {key[0]}",
                    })

    # Deduplicate ops (avoid double-delete entries)
    seen = set()
    unique_ops = []
    for op in ops:
        sig = (op["action"], op["url"], op["username"], op.get("newUsername", ""))
        if sig in seen:
            continue
        seen.add(sig)
        unique_ops.append(op)

    plan = {"ops": unique_ops}
    with open(args.out, "w") as f:
        json.dump(plan, f, indent=2)
    print(f"wrote {len(unique_ops)} ops to {args.out}", file=sys.stderr)
    # summary
    by_action = defaultdict(int)
    for op in unique_ops:
        by_action[op["action"]] += 1
    for k, v in sorted(by_action.items()):
        print(f"  {k}: {v}", file=sys.stderr)


if __name__ == "__main__":
    main()
