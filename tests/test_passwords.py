from relay.auth.passwords import hash_password, verify_password


def test_hash_is_not_the_password() -> None:
    password = "en un lugar de la mancha"
    assert hash_password(password) != password


def test_same_password_gets_different_hashes() -> None:
    password = "same password!"
    assert hash_password(password) != hash_password(password)


def test_verify_password() -> None:
    password = "en un lugar de la mancha"
    hashed = hash_password(password)
    assert verify_password(hashed, password)
    assert not verify_password(hashed, "wrong password")
