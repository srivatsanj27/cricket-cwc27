"""Team names and ICC membership."""

FULL_MEMBERS = frozenset(
    {
        "Afghanistan",
        "Australia",
        "Bangladesh",
        "England",
        "India",
        "Ireland",
        "New Zealand",
        "Pakistan",
        "South Africa",
        "Sri Lanka",
        "West Indies",
        "Zimbabwe",
    }
)

_ALIASES = {
    "U.A.E.": "United Arab Emirates",
    "UAE": "United Arab Emirates",
    "USA": "United States of America",
    "U.S.A.": "United States of America",
}


def normalise_team(name: str) -> str:
    """Map a raw team name to its canonical form."""
    stripped = name.strip()
    if not stripped:
        raise ValueError("team name is blank")
    return _ALIASES.get(stripped, stripped)


def is_full_member(team: str) -> bool:
    return normalise_team(team) in FULL_MEMBERS
