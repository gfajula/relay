import uuid
from datetime import timedelta

import jwt
import pytest

from relay.auth.tokens import create_access_token, decode_access_token

SECRET = "test-secret-" + "x" * 32
OTHER_SECRET = "test-secret-" + "y" * 32


def test_access_token_round_trip() -> None:
    user_id = uuid.uuid4()
    token = create_access_token(user_id, SECRET, timedelta(minutes=5))
    assert decode_access_token(token, SECRET) == user_id


def test_expired_token_is_rejected() -> None:
    token = create_access_token(uuid.uuid4(), SECRET, timedelta(seconds=-1))
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(token, SECRET)


def test_token_signed_with_other_secret_is_rejected() -> None:
    token = create_access_token(
        uuid.uuid4(), OTHER_SECRET, timedelta(minutes=5)
    )
    with pytest.raises(jwt.InvalidSignatureError):
        decode_access_token(token, SECRET)
