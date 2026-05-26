#!/usr/bin/env python3
"""
Cleanup workflow for Apple Passwords on macOS 15.4+ where the helper binary
is locked down. Operates entirely on a CSV export from Passwords.app.

Pipeline:
  Passwords.app  --File→Export→Passwords-->  in.csv
  cleanup-csv.py --in in.csv --out cleaned.csv --report report.md
  Passwords.app  --select all→delete-->  (empty)
  Passwords.app  --File→Import-->  cleaned.csv

Produces:
  cleaned.csv  - deduped, normalized, ready to import
  report.md    - human-readable summary of what changed

Usage:
  python3 cleanup-csv.py --in ~/Downloads/Passwords.csv --out ~/Downloads/cleaned.csv --report ~/Downloads/report.md
  python3 cleanup-csv.py --in passwords.csv --out cleaned.csv --aggressive
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


def service_name(domain: str) -> str:
    overrides = {
        "americanexpress.com": "American Express",
        "bankofamerica.com": "Bank of America",
        "wellsfargo.com": "Wells Fargo",
        "freetaxusa.com": "FreeTaxUSA",
        "collegeboard.org": "College Board",
        "vestiairecollective.com": "Vestiaire",
        "stockx.com": "StockX",
        "lafitness.com": "LA Fitness",
        "hbomax.com": "HBO Max",
        "youtube.com": "YouTube",
        "linkedin.com": "LinkedIn",
        "tmobile.com": "T-Mobile",
        "att.com": "AT&T",
        "soundcloud.com": "SoundCloud",
        "doordash.com": "DoorDash",
        "openai.com": "OpenAI",
        "github.com": "GitHub",
    }
    rd = root_domain(domain)
    if rd in overrides:
        return overrides[rd]
    base = (rd or domain).split(".")[0]
    return base.capitalize() if base else "Unknown"


def normalize_user(u: str) -> str:
    u = u.strip()
    if "@" in u and u.lower().endswith(".con"):
        u = u[:-4] + ".com"
    return u


def is_junk_user(u: str) -> bool:
    u = u.strip().lower()
    if u in {"true", "false", "null", "undefined", "none", "n/a", "na", ""}:
        return True
    if re.match(r"^[—–\-]+$", u):
        return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True, help="path to Passwords.app CSV export")
    ap.add_argument("--out", required=True, help="path to write cleaned CSV")
    ap.add_argument("--report", help="path to write markdown report (optional)")
    ap.add_argument("--aggressive", action="store_true",
                    help="dedupe subdomain variants of same root domain (e.g. login.x.com + portal.x.com -> x.com)")
    args = ap.parse_args()

    rows = []
    with open(args.inp) as f:
        reader = csv.DictReader(f)
        original_fields = reader.fieldnames or []
        for row in reader:
            rows.append(row)

    if not rows:
        print("no rows in input CSV", file=sys.stderr)
        sys.exit(1)
    print(f"loaded {len(rows)} entries from {args.inp}", file=sys.stderr)

    changes = {
        "removed_dupes": [],
        "renamed_titles": [],
        "fixed_users": [],
        "removed_junk": [],
        "subdomain_merges": [],
    }

    # Pass 1: normalize usernames + drop junk
    cleaned = []
    for r in rows:
        u_raw = r.get("Username", "") or ""
        u_norm = normalize_user(u_raw)
        if u_norm != u_raw and u_raw.strip():
            changes["fixed_users"].append({"title": r.get("Title", ""), "old": u_raw, "new": u_norm})
            r["Username"] = u_norm
        # Drop entries where the username is junk AND no password (probably empty rows)
        if is_junk_user(u_norm) and not r.get("Password", "").strip():
            changes["removed_junk"].append({"title": r.get("Title", ""), "user": u_raw})
            continue
        cleaned.append(r)

    # Pass 2: dedupe by (domain, username)
    seen = {}
    deduped = []
    for r in cleaned:
        url = r.get("URL", "") or r.get("Url", "") or ""
        dom = domain_of(url)
        user_key = (r.get("Username", "") or "").lower().strip()
        key = (dom, user_key)
        if not dom:
            deduped.append(r)
            continue
        if key in seen:
            changes["removed_dupes"].append({
                "title": r.get("Title", ""),
                "url": url,
                "user": r.get("Username", ""),
                "kept": seen[key].get("Title", ""),
            })
            continue
        seen[key] = r
        deduped.append(r)

    # Pass 3 (optional): aggressive subdomain merge
    if args.aggressive:
        seen_root = {}
        final = []
        for r in deduped:
            url = r.get("URL", "") or ""
            dom = domain_of(url)
            user_key = (r.get("Username", "") or "").lower().strip()
            if not dom:
                final.append(r)
                continue
            rd = root_domain(dom)
            key = (rd, user_key)
            existing = seen_root.get(key)
            if existing is None:
                seen_root[key] = r
                final.append(r)
            else:
                # Already have an entry on this root domain for this user.
                # Prefer the one with the shortest domain (most likely the root).
                if len(domain_of(existing.get("URL", ""))) > len(dom):
                    # replace
                    final.remove(existing)
                    seen_root[key] = r
                    final.append(r)
                    changes["subdomain_merges"].append({
                        "kept": r.get("URL", ""),
                        "dropped": existing.get("URL", ""),
                        "user": r.get("Username", ""),
                    })
                else:
                    changes["subdomain_merges"].append({
                        "kept": existing.get("URL", ""),
                        "dropped": url,
                        "user": r.get("Username", ""),
                    })
        deduped = final

    # Pass 4: title normalization for entries whose Title looks like a raw domain
    for r in deduped:
        title = (r.get("Title", "") or "").strip()
        url = r.get("URL", "") or ""
        dom = domain_of(url)
        # Match "www.amazon.com (user)" or just "www.amazon.com" patterns
        if dom and re.match(r"^(?:https?://)?(?:www\.)?[a-z0-9.-]+\.[a-z]{2,}", title.lower()):
            new_title = service_name(dom)
            if new_title != title:
                changes["renamed_titles"].append({"old": title, "new": new_title})
                r["Title"] = new_title

    # Write cleaned CSV
    out_fields = original_fields if original_fields else list(deduped[0].keys())
    with open(args.out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=out_fields)
        writer.writeheader()
        for r in deduped:
            writer.writerow(r)

    print(f"wrote {len(deduped)} entries to {args.out}", file=sys.stderr)
    print(f"  removed dupes:       {len(changes['removed_dupes'])}", file=sys.stderr)
    print(f"  subdomain merges:    {len(changes['subdomain_merges'])}", file=sys.stderr)
    print(f"  renamed titles:      {len(changes['renamed_titles'])}", file=sys.stderr)
    print(f"  fixed usernames:     {len(changes['fixed_users'])}", file=sys.stderr)
    print(f"  removed junk:        {len(changes['removed_junk'])}", file=sys.stderr)

    # Write report
    if args.report:
        with open(args.report, "w") as f:
            f.write("# Apple Passwords Cleanup Report\n\n")
            f.write(f"- Source: `{args.inp}`\n")
            f.write(f"- Output: `{args.out}`\n")
            f.write(f"- Aggressive mode: `{args.aggressive}`\n\n")
            f.write(f"## Summary\n\n")
            f.write(f"| Action | Count |\n|---|---|\n")
            f.write(f"| Removed exact duplicates | {len(changes['removed_dupes'])} |\n")
            f.write(f"| Removed subdomain duplicates | {len(changes['subdomain_merges'])} |\n")
            f.write(f"| Renamed titles | {len(changes['renamed_titles'])} |\n")
            f.write(f"| Fixed username typos/casing | {len(changes['fixed_users'])} |\n")
            f.write(f"| Removed junk entries | {len(changes['removed_junk'])} |\n")
            f.write(f"| **Final entries** | **{len(deduped)}** |\n\n")
            for section, key, header in [
                ("Removed exact duplicates", "removed_dupes", "| title | url | user | kept-instead |\n|---|---|---|---|\n"),
                ("Removed subdomain duplicates", "subdomain_merges", "| kept | dropped | user |\n|---|---|---|\n"),
                ("Renamed titles", "renamed_titles", "| old | new |\n|---|---|\n"),
                ("Fixed usernames", "fixed_users", "| title | old | new |\n|---|---|---|\n"),
                ("Removed junk", "removed_junk", "| title | user |\n|---|---|\n"),
            ]:
                if changes[key]:
                    f.write(f"\n## {section} ({len(changes[key])})\n\n")
                    f.write(header)
                    for c in changes[key]:
                        vals = list(c.values())
                        f.write("| " + " | ".join(str(v) for v in vals) + " |\n")
        print(f"report: {args.report}", file=sys.stderr)


if __name__ == "__main__":
    main()
