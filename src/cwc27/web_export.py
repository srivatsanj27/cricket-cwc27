"""Ratings and venues as JSON for the fantasy-series website in web/."""

import json
from collections import Counter
from collections.abc import Iterable, Mapping
from datetime import date, datetime
from pathlib import Path
from typing import Any

from cwc27.models import Match
from cwc27.ratings.elo import EloConfig, run_elo
from cwc27.teams import is_full_member
from cwc27.venues import home_team

RATING_DECIMALS = 1


def build_web_export(
    matches: Iterable[Match],
    config: EloConfig,
    city_countries: Mapping[str, str],
    generated_at: datetime,
    active_since: date,
) -> dict[str, Any]:
    """Current ratings for every team that has played since `active_since`, plus venues.

    Ratings learn from every match given; `active_since` only decides who is listed.
    Raises ValueError if no match was played since `active_since`.
    """
    all_matches = sorted(matches, key=lambda m: m.date)
    recent = [m for m in all_matches if m.date >= active_since]
    if not recent:
        raise ValueError(f"No matches since {active_since.isoformat()}")

    ratings = run_elo(all_matches, config, lambda m: home_team(m, city_countries))
    recent_counts = Counter(team for m in recent for team in (m.team_a, m.team_b))
    teams = sorted(recent_counts, key=lambda team: ratings[team], reverse=True)

    return {
        "generated_at": generated_at.isoformat(),
        "ratings_through": all_matches[-1].date.isoformat(),
        "matches_rated": len(all_matches),
        "elo": {"home_advantage": config.home_advantage, "scale": config.scale},
        "teams": [
            {
                "name": team,
                "rating": round(ratings[team], RATING_DECIMALS),
                "matches": recent_counts[team],
                "full_member": is_full_member(team),
            }
            for team in teams
        ],
        "venues": [
            {"city": city, "country": country}
            for city, country in sorted(city_countries.items(), key=lambda cc: (cc[1], cc[0]))
        ],
    }


def write_web_export(path: Path, payload: Mapping[str, Any]) -> None:
    """Write via a temporary file so the site never sees a half-written JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n")
    temporary.replace(path)
