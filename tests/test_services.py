import pytest

from app.services import validate_identifier


def test_mmsi_validation():
    assert validate_identifier("MMSI", "123456789") == "123456789"
    with pytest.raises(ValueError):
        validate_identifier("MMSI", "123")


def test_imo_check_digit_validation():
    assert validate_identifier("IMO", "IMO 9074729") == "9074729"
    with pytest.raises(ValueError):
        validate_identifier("IMO", "9074728")
