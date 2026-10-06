import pytest

from cwc27.teams import FULL_MEMBERS, is_full_member, normalise_team


def test_there_are_twelve_full_members():
    assert len(FULL_MEMBERS) == 12


@pytest.mark.parametrize("team", ["India", "Ireland", "Zimbabwe", "Afghanistan"])
def test_full_members(team):
    assert is_full_member(team)


@pytest.mark.parametrize("team", ["Namibia", "Netherlands", "Scotland", "Nepal"])
def test_associates(team):
    assert not is_full_member(team)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("U.A.E.", "United Arab Emirates"),
        ("UAE", "United Arab Emirates"),
        ("USA", "United States of America"),
        ("  India ", "India"),
    ],
)
def test_normalise_team(raw, expected):
    assert normalise_team(raw) == expected


def test_normalise_rejects_blank():
    with pytest.raises(ValueError):
        normalise_team("   ")
