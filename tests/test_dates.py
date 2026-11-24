import pytest

from utils.dates import to_iso_date


@pytest.mark.parametrize(
    "text, expected",
    [
        ("14 giugno 1751", "1751-06-14"),
        ("September 29, 1932", "1932-09-29"),
        ("29 de Junho de 1958", "1958-06-29"),
        ("1º de maio de 1891", "1891-05-01"),
        ("15 de mayo de 1931", "1931-05-15"),
        ("1er janvier 1900", "1900-01-01"),
        ("3 février 1892", "1892-02-03"),
        ("die 8 mensis Decembris 1864", "1864-12-08"),
        ("24 de maio de 2015", "2015-05-24"),
        ("1751", "1751"),
        ("Anno Domini 1750", "1750"),
        ("", None),
        ("sem data", None),
    ],
)
def test_to_iso_date(text, expected):
    assert to_iso_date(text) == expected
