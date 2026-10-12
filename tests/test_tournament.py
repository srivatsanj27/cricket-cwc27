import pytest

from cwc27.simulate.tournament import (
    QUALIFIER_WINNER,
    SUPER_SERIES_WINNER,
    WorldCupFormat,
    host_predictor,
    load_format,
    simulate_world_cup,
)

GROUP_A = ("A1", "A2", "A3", "A4", "A5", QUALIFIER_WINNER)
GROUP_B = ("B1", "B2", "B3", "B4", "B5", SUPER_SERIES_WINNER)
QUALIFIER = ("Q1", "Q2", "Q3", "Q4", "Q5")
FORMAT = WorldCupFormat(groups=(GROUP_A, GROUP_B), qualifier=QUALIFIER, hosts=("A1",))

TOML = """
hosts = ["A1"]

[groups]
A = ["A1", "A2", "A3", "A4", "A5", "Qualifier winner"]
B = ["B1", "B2", "B3", "B4", "B5", "Super Series winner"]

[qualifier]
teams = ["Q1", "Q2", "Q3", "Q4", "Q5"]
"""


def coin(team_a, team_b):
    return 0.5


def always_wins(star):
    def predict(team_a, team_b):
        if star in (team_a, team_b):
            return 1.0 if team_a == star else 0.0
        return 0.5

    return predict


def test_format_loads_from_toml(tmp_path):
    path = tmp_path / "format.toml"
    path.write_text(TOML)

    assert load_format(path) == FORMAT


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ('"A2", "A3"', '"A2", "A2"', "more than once"),
        ('"Super Series winner"', '"B6"', "Super Series winner"),
        ('"Q3", "Q4", "Q5"', '"Q3"', "at least four"),
        ('"Q5"]', '"Q5", "A3"]', "more than once"),
        ('B = ["B1", "B2", "B3", "B4", "B5", "Super Series winner"]', 'B = "B1"', "list of"),
        ('hosts = ["A1"]', 'hosts = ["A1", 7]', "list of"),
    ],
)
def test_bad_formats_are_rejected(tmp_path, old, new, message):
    path = tmp_path / "format.toml"
    path.write_text(TOML.replace(old, new))

    with pytest.raises(ValueError, match=message):
        load_format(path)


def test_stage_probabilities_add_up_to_the_places_in_each_stage():
    forecast = simulate_world_cup(FORMAT, coin, n_sims=2_000, seed=1)

    totals = {
        stage: sum(getattr(odds, stage) for odds in forecast.values())
        for stage in ("group_stage", "super7", "semi_final", "final", "champion")
    }
    assert totals == pytest.approx(
        {"group_stage": 12, "super7": 7, "semi_final": 4, "final": 2, "champion": 1}
    )
    assert forecast["A1"].group_stage == 1.0
    assert set(forecast) == set(GROUP_A[:5] + GROUP_B[:5] + QUALIFIER)


def test_an_unbeatable_qualifier_team_wins_the_cup():
    forecast = simulate_world_cup(FORMAT, always_wins("Q3"), n_sims=200, seed=2)

    assert forecast["Q3"].group_stage == 1.0
    assert forecast["Q3"].champion == 1.0


def test_the_same_seed_gives_the_same_forecast():
    first = simulate_world_cup(FORMAT, coin, n_sims=300, seed=7)

    assert simulate_world_cup(FORMAT, coin, n_sims=300, seed=7) == first


def test_the_qualifier_can_use_its_own_predictor():
    forecast = simulate_world_cup(
        FORMAT, coin, n_sims=200, seed=3, qualifier_predict=always_wins("Q1")
    )

    assert forecast["Q1"].group_stage == 1.0
    assert forecast["Q1"].champion < 1.0


def test_qualifier_hosts_are_optional_and_load_when_given(tmp_path):
    path = tmp_path / "format.toml"
    path.write_text(TOML.replace("[qualifier]", '[qualifier]\nhosts = ["Q1"]'))

    assert load_format(path).qualifier_hosts == ("Q1",)
    assert FORMAT.qualifier_hosts == ()


def test_n_sims_must_be_positive():
    with pytest.raises(ValueError, match="n_sims"):
        simulate_world_cup(FORMAT, coin, n_sims=0)


def test_hosts_get_home_advantage_except_against_each_other():
    calls = []

    def predict(team_a, team_b, home):
        calls.append(home)
        return 0.5

    play = host_predictor(predict, hosts=("SA", "ZIM"))
    play("SA", "IND")
    play("IND", "ZIM")
    play("IND", "AUS")
    play("SA", "ZIM")

    assert calls == ["SA", "ZIM", None, None]


def test_the_real_2027_format_loads():
    fmt = load_format()

    assert [len(group) for group in fmt.groups] == [6, 6]
    assert len(fmt.qualifier) == 10
