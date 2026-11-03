"""
One-time cleanup: give an expiry to rate-limit counters that have none.

Context (hotfix 2026-11-03): before the fix, check_rate_limit never applied an expiry to
the env-prefixed counter, so every rate-limit key lived forever. The fixed code repairs a
key when it is next accessed; this script handles keys that may never be accessed again
(e.g. an IP that never returns), so no expiry-less rate-limit key is left behind.

Run AFTER the fix is deployed, from the backend service shell on Render:
    .venv/bin/python ops/redis_ratelimit_ttl_cleanup.py            # dry run (default)
    .venv/bin/python ops/redis_ratelimit_ttl_cleanup.py --apply    # apply
    .venv/bin/python ops/redis_ratelimit_ttl_cleanup.py            # verify: no_ttl must be 0

What it touches: only keys shaped `<env>:ratelimit:...` (second segment exactly
"ratelimit"), of type string, with no expiry (TTL -1). It never deletes anything: it sets
EXPIRE <window> NX, so each key disappears within one window, and a key that has gained an
expiry in the meantime (e.g. repaired by live traffic) is left untouched.

Reversibility: dry run first shows exactly what would change. Once applied, the counters
expire within one window and are not restorable — which is harmless: losing a counter
resets one rate-limit window, the same thing the fixed code does every minute.

Output contains key families and counts only — never full keys (they contain client IPs
and login_hint values).
"""

import argparse
import collections
import os
import sys

import redis

SCAN_PATTERN = "*ratelimit:*"


def is_ratelimit_key(key: str) -> bool:
    """True for `<env>:ratelimit:...` keys only."""
    parts = key.split(":")
    return len(parts) >= 3 and parts[1] == "ratelimit"


def family(key: str) -> str:
    """`production:ratelimit:oauth:token:<client>:<ip>` -> `production:ratelimit:oauth:token`."""
    return ":".join(key.split(":")[:4])


def run(r: "redis.Redis", apply: bool, window: int) -> dict:
    """Scan rate-limit keys; when apply is True, give expiry-less ones an expiry."""
    stats = collections.defaultdict(lambda: collections.Counter())
    for key in r.scan_iter(match=SCAN_PATTERN, count=500):
        if not is_ratelimit_key(key):
            continue
        s = stats[family(key)]
        s["total"] += 1
        if r.ttl(key) != -1:
            continue
        if r.type(key) != "string":
            s["skipped_not_string"] += 1
            continue
        s["no_ttl"] += 1
        if apply:
            # NX: only if the key still has no expiry at this moment
            if r.expire(key, window, nx=True):
                s["expiry_set"] += 1
            else:
                s["skipped_gained_ttl"] += 1
    return {f: dict(c) for f, c in sorted(stats.items())}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--apply", action="store_true", help="set the expiry (default: dry run)")
    parser.add_argument("--window", type=int, default=60, help="expiry in seconds (default 60)")
    args = parser.parse_args(argv)

    r = redis.from_url(os.environ["REDIS_URL"], decode_responses=True)
    print(f"ENV={os.environ.get('ENV')} redis={r.info('server')['redis_version']} "
          f"mode={'APPLY' if args.apply else 'DRY RUN'} window={args.window}s")
    result = run(r, apply=args.apply, window=args.window)
    if not result:
        print("no rate-limit keys found")
    for fam, counts in result.items():
        print(fam, " ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
