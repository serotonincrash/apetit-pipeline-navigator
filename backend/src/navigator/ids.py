"""Record ids: a type prefix and a time-sortable unique part, such as run_01JC4Z...

The unique part follows the ULID layout: 48 bits of milliseconds since 1970, then 80 random
bits, written in Crockford base 32. Ids made later sort after ids made earlier.
"""

import secrets
import time

_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

PREFIXES = {
    "run": "run",
    "step_run": "step",
    "run_event": "evt",
    "artifact": "art",
    "source_file": "src",
    "proposal": "prop",
    "decision": "dec",
    "rule": "rule",
    "result_set": "rs",
    "metric": "met",
    "assumption": "asm",
    "action": "act",
    "action_option": "opt",
}


def _encode(value: int, length: int) -> str:
    chars: list[str] = []
    for _ in range(length):
        value, rem = divmod(value, 32)
        chars.append(_ALPHABET[rem])
    return "".join(reversed(chars))


def new_id(kind: str) -> str:
    """A new id for a record of `kind`, one of the keys of PREFIXES."""
    millis = int(time.time() * 1000)
    value = (millis << 80) | secrets.randbits(80)
    return f"{PREFIXES[kind]}_{_encode(value, 26)}"
