"""Access token generation.

The access token is the only thing that grants entry to a chat. The HN does
not: it is guessable, sequential and shared between colleagues.
See DECISIONS.md section 6.
"""

import secrets

# 32 bytes of entropy, rendered as 64 hex characters, which is exactly the
# width of requests.access_token (CHAR(64)).
TOKEN_BYTES = 32


def generate_access_token() -> str:
    """Return a fresh access token.

    `secrets`, never `random`. The `random` module is a Mersenne Twister
    seeded from the clock: observing a few outputs is enough to predict the
    rest. `secrets` draws from the OS cryptographic source, which is what
    makes a token unguessable.

    32 bytes is 256 bits. Guessing one is not a practical attack, which is
    why the link itself can be the credential.
    """
    return secrets.token_hex(TOKEN_BYTES)
