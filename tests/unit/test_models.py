from position_tracker.models import mask_account_number


def test_mask_account_number_keeps_last_four() -> None:
    assert mask_account_number("Z12345678") == "...5678"


def test_mask_account_number_short_number() -> None:
    assert mask_account_number("12") == "...12"
