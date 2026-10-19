import secrets

KEY_PREFIX = "rly_"


def generate_api_key() -> tuple[str, str]:
    prefix = KEY_PREFIX + secrets.token_hex(6)
    key = f"{prefix}_{secrets.token_urlsafe(32)}"
    return key, prefix
