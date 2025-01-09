import pytest

from jg.plucker.meetups_pehapkari.spider import fix_url


@pytest.mark.parametrize(
    "url, expected",
    [
        (
            "www.facebook.com/events/1118251933124168",
            "https://www.facebook.com/events/1118251933124168",
        ),
        (
            "https://www.meetup.com/pra%C5%BEske-srazy-p%C5%99atel-php-pehapkari-cz/events/305454246/",
            "https://www.meetup.com/pra%C5%BEske-srazy-p%C5%99atel-php-pehapkari-cz/events/305454246/",
        ),
    ],
)
def test_fix_url(url: str, expected: str):
    assert fix_url(url) == expected
