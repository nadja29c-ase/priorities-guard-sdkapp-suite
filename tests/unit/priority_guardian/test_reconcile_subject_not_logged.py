"""
The raw `openai/subject` must never reach the logs.

WHY THIS MATTERS. The subject is the one value an attacker needs to exploit the
reconciliation path: supplying a victim's subject in `_meta` can, when the caller's own
account is a fresh shell, make case C1 return the victim's canonical user_id — which now
reaches an irreversible deletion tool. The subject is opaque and never shown to users, so
the log store was the only place it was being published.

THIS DOES NOT FIX TASK #10. A subject leaked any other way still works. These tests pin the
one channel that was closed, so it cannot quietly reopen — a sixth log site added later with
`subject=openai_subject` would fail here.
"""

import inspect
import re

import pytest

from backend.apps.priority_guardian.routers import reconcile_router
from backend.apps.priority_guardian.routers.reconcile_router import _subject_fingerprint

RAW_SUBJECT = "user_2abcXYZ_openai_opaque_subject_value_9876543210"


def test_fingerprint_does_not_contain_the_raw_subject():
    """
    Bug this catches: a "fingerprint" that embeds or lightly encodes the input — a prefix, a
    suffix, base64, a reversible transform. The whole point is that the log value cannot be
    turned back into the exploit input.
    """
    fp = _subject_fingerprint(RAW_SUBJECT)

    assert RAW_SUBJECT not in fp
    for chunk_len in (8, 12, 16):
        for i in range(0, len(RAW_SUBJECT) - chunk_len):
            assert RAW_SUBJECT[i:i + chunk_len] not in fp, (
                f"fingerprint leaks a {chunk_len}-char substring of the subject"
            )


def test_fingerprint_is_stable_so_log_lines_can_be_correlated():
    """
    Bug this catches: a random or time-seeded value. The point of hashing rather than
    redacting is that two log lines about the SAME subject remain joinable during an
    investigation. A per-call random token would destroy that and look identical in review.
    """
    assert _subject_fingerprint(RAW_SUBJECT) == _subject_fingerprint(RAW_SUBJECT)
    assert _subject_fingerprint(RAW_SUBJECT) != _subject_fingerprint(RAW_SUBJECT + "x")


def test_fingerprint_is_short_enough_to_be_useless_as_input():
    """
    Bug this catches: logging the full SHA-256. A complete digest of a low-entropy or
    enumerable value is closer to the original than a truncation is, and offers no
    correlation benefit over 12 hex chars.
    """
    fp = _subject_fingerprint(RAW_SUBJECT)

    assert fp.startswith("sha256:"), "the value should be self-describing in logs"
    assert re.fullmatch(r"sha256:[0-9a-f]{12}", fp), fp


def test_no_log_call_in_the_module_passes_the_raw_subject():
    """
    Bug this catches: a SIXTH log site added later with `subject=openai_subject`. The five
    known sites were fixed; nothing structural stops a new one being written the old way,
    and a reviewer would have no reason to notice.

    Reads the module source rather than trusting the five known line numbers, so it keeps
    working as the file moves.
    """
    src = inspect.getsource(reconcile_router)
    code = "\n".join(
        line for line in src.splitlines() if not line.strip().startswith("#")
    )

    # NB: `.values(openai_subject=openai_subject)` legitimately CONTAINS the substring
    # "subject=openai_subject". A naive `in` check matches the stored value and fails on
    # correct code — the first version of this test did exactly that. Anchor on the keyword
    # boundary so only a bare `subject=` argument matches.
    leaks = re.findall(r"[\s(]subject=openai_subject", code)
    assert not leaks, (
        "a log call passes the raw subject — use _subject_fingerprint(openai_subject)"
    )
    assert code.count("subject_fp=_subject_fingerprint(openai_subject)") == 5, (
        "expected exactly five fingerprinted log sites; a site was added or removed"
    )


def test_the_stored_subject_is_still_raw():
    """
    Bug this catches: hashing what is PERSISTED rather than only what is logged. The stored
    value backs the partial unique index ix_core_users_openai_subject and the lookup in
    _reconcile_user_by_subject. Hashing it would silently break cross-device reconciliation
    for every existing user — a far worse outcome than the leak being closed.
    """
    src = inspect.getsource(reconcile_router)

    assert "CoreUser.openai_subject == openai_subject" in src, (
        "the lookup must compare the RAW subject"
    )
    assert ".values(openai_subject=openai_subject)" in src, (
        "the stamp must store the RAW subject"
    )
    assert "_subject_fingerprint" not in src.split("Step 1: Lookup by subject")[1].split(
        "log.info"
    )[0], "the fingerprint leaked into the lookup path"


@pytest.mark.parametrize(
    "event",
    [
        "reconcile.first_bind",
        "reconcile.race_lost",
        "reconcile.race_lost_no_winner",
        "reconcile.cross_device",
        "reconcile.ambiguous_collision",
    ],
)
def test_each_known_log_event_carries_a_fingerprint_not_a_subject(event):
    """
    Bug this catches: fixing four of the five sites. Each event is checked individually, so a
    single missed call site fails with the event name that still leaks rather than a generic
    count mismatch.
    """
    src = inspect.getsource(reconcile_router)

    # Take the log call's argument list: from the event name to the line that closes the
    # call. Splitting on the first ")" lands inside str(jwt_user_id) — the first version of
    # this test did that and read an empty block, failing on correct code.
    after = src.split(f'"{event}"', 1)[1]
    block = after.split("\n        )", 1)[0].split("\n            )", 1)[0]

    assert re.search(r"[\s(]subject=openai_subject", block) is None, (
        f"{event} still logs the raw subject"
    )
    assert "_subject_fingerprint" in block, f"{event} logs no subject fingerprint at all"
