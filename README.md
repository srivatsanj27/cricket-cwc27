# cricket-cwc27

A data-driven predictor for men's ODI cricket in the build-up to the ICC Cricket World Cup 2027.

It tracks every men's ODI and updates itself every day to predict:

- **Matches:** win probabilities for upcoming ODIs, bilateral series and tri-series
- **Squads:** the likely World Cup 15 for each nation
- **The World Cup:** each team's chance of reaching every stage and winning the title, including the CWC qualifiers

Every match prediction is logged and locked the day before the game, then scored on the result, so the model's track record is public.

## Live

| What | Where |
|---|---|
| Dashboard: World Cup odds, next matches, Elo over time, track record | [srivatsanj27.github.io/cricket-cwc27/dashboard.html](https://srivatsanj27.github.io/cricket-cwc27/dashboard.html) |
| Fantasy series: pick two teams and the venues, play the series 20,000 times | [srivatsanj27.github.io/cricket-cwc27](https://srivatsanj27.github.io/cricket-cwc27/) |
| Prediction log | [data/predictions_log.csv](data/predictions_log.csv) |
| Upcoming fixtures | [data/fixtures.csv](data/fixtures.csv) |
| Results entered by hand | [data/manual/](data/manual/) |

## How it works

### Match predictions

- **Data:** every men's ODI from Cricsheet, plus results entered by hand where Cricsheet has none. Cricsheet withholds Afghanistan's matches from Nov 2024, so their 82 ODIs since 2019 were entered from ESPNcricinfo. Ball-by-ball data since 2019 is used for player ratings. Everything is stored in DuckDB.
- **Elo ratings:** each result updates both teams' ratings, with a home advantage. The tuned settings are K = 25 and 80 points of home advantage.
- **Backtest:** walk-forward, so each match is predicted only from earlier results. Settings were tuned on 2021 to the 2023 World Cup, then checked on matches since. On those later matches, Elo scores a Brier of 0.224, against 0.241 for "the team with the better win rate" and 0.247 for a coin flip (lower is better).
- **Series:** Monte Carlo simulation of bilateral series and tri-series (round robin plus a final).

### Squads

- **Player ratings:** runs above average per 100 balls, for batting and for bowling. They are adjusted for the strength of the opposition and weighted towards recent matches.
- **Roles:** keeper, batter, all-rounder or bowler, and pace or spin. These are worked out from the data, with hand corrections in `config/player_overrides.csv`.
- **Picker:** chooses 15 players from how often selectors have picked them lately and how good they are. It keeps a balanced squad: at least 2 keepers, 2 spinners, 4 pacers and 7 bowling options.
- **Certain picks:** stars who play whenever fit, such as Bumrah, Cummins and Rabada, are always included. The list is in `config/certain_picks.csv`.
- **Backtest:** the picker named 11.7 of 15 correctly on average for the 2023 World Cup, and 11.4 of 15 for the 2025 Champions Trophy.

### The World Cup

- **Format:** the ICC's 2027 format, as set in July 2026. The Qualifier winner goes straight into the group stage, and the Qualifier's 2nd to 4th play a 3-team Super Series for one more group place. Two groups of six follow, then a Super 7 (the top three of each group plus the better fourth-placed team), then semi-finals and the final.
- **Simulation:** the whole event is played 10,000 times from current Elo, with home advantage for the hosts.
- **Rating uncertainty:** ratings drift over time, so each team's rating is blurred in every simulated tournament. The amount was fitted on past matches by predicting them from ratings frozen months earlier. It comes to about 60 Elo points for tomorrow's match and about 100 a year ahead, and it shrinks automatically as the tournament gets closer.
- **Assumptions** are listed in `config/wc2027_format.toml`. Five of the ten Qualifier teams are still guesses until League 2 and the Qualifier Play-off finish.

## Automation

- **Tests:** every push runs the Python and lint checks on GitHub Actions.
- **Daily job (00:30 UTC):** downloads the latest Cricsheet data, scores finished predictions and locks in the next day's. It then refreshes the website data and commits anything that changed.
- **Publishing:** the website in `web/` goes to GitHub Pages after each change and after each daily run.

Cricsheet usually publishes matches a few weeks late. Recent results go in by hand (see "After each match").

## Setup

Needs Python 3.12 or newer.

```bash
python3 -m venv .venv
```

```bash
.venv/bin/pip install -e ".[dev]"
```

```bash
source .venv/bin/activate
```

Then download the Cricsheet data and build the database:

```bash
cwc27 ingest --download
```

## Commands

| Command | What it does |
|---|---|
| `cwc27 ingest [--download]` | Load Cricsheet ODIs (and `data/manual/*.csv`) into the database |
| `cwc27 result DATE TEAM_A TEAM_B --winner TEAM [--runs N or --wickets N] [--dls]` | Record a finished match Cricsheet hasn't published yet. Use `--tie` or `--no-result` instead of `--winner` when needed |
| `cwc27 update [--download]` | Ingest, re-rate, score the prediction log and predict upcoming fixtures |
| `cwc27 export-web` | Write `web/data/ratings.json` for the fantasy page, and `web/data/dashboard.json` with ratings over time, predictions, the track record and World Cup odds |
| `cwc27 backtest [--k K] [--home-advantage H]` | Score Elo and the baselines on past ODIs |
| `cwc27 tune` | Grid-search Elo settings and confirm them on recent matches |
| `cwc27 squads [--team TEAM] [--as-of DATE]` | Predict each World Cup team's squad of 15 |
| `cwc27 squad-backtest` | Score the squad picker against the 2023 World Cup and 2025 Champions Trophy squads |
| `cwc27 worldcup [--sims N] [--seed S] [--rating-sd SD]` | Simulate the 2027 World Cup from current Elo |

### After each match

If Cricsheet doesn't have the match yet, record it and push. The daily job does the rest.

```bash
cwc27 result 2026-10-18 Pakistan "Sri Lanka" --winner Pakistan --runs 25
```

```bash
git add data/manual && git commit -m "data: result" && git push
```

To see the effect straight away instead, run `cwc27 update` and `cwc27 export-web` locally. Then commit `data/` and `web/data/`.

## Run the website locally

```bash
python3 -m http.server 8027 --directory web
```

Then open http://localhost:8027 for the fantasy series, or http://localhost:8027/dashboard.html for the dashboard. More detail is in [web/README.md](web/README.md).

## Tests

```bash
pytest
```

```bash
cd web && npm test
```

## Project layout

```
src/cwc27/
  ingest/          Cricsheet and manual-results loaders
  ratings/         Elo engine and model wrapper
  players/         player ratings, roles, squad parsing and the squad picker
  evaluation/      backtest, metrics, baselines, tuning, rating uncertainty
  simulate/        series, tri-series and World Cup simulation
  tracking/        prediction log and the daily update loop
  web_export.py    ratings JSON for the fantasy page
  web_dashboard.py data for the dashboard
  cli.py           the cwc27 command
config/            World Cup format, certain picks, role overrides, venue countries
data/              fixtures, manual results, past squads, prediction log
                   (raw data and the database are not committed)
web/               fantasy series page and dashboard (static HTML, CSS and JavaScript)
tests/             pytest suite
.github/workflows/ tests, daily update, GitHub Pages
```

## Roadmap

- [x] Match predictions, series and tri-series simulation, public prediction log
- [x] Player ratings, roles and predicted World Cup squads
- [x] World Cup 2027 simulation with rating uncertainty
- [x] Daily automatic updates and a public dashboard
- [ ] Margin of victory in Elo, and faster-reacting ratings
- [ ] Match predictions that account for the XIs, once player ratings are comparable across teams
- [ ] What-if tool (for example, a team without its best bowler), par scores by venue, player award predictions

## Data

Ball-by-ball match data comes from [Cricsheet](https://cricsheet.org), which is openly licensed. Raw data is downloaded by the pipeline and not stored in this repository. Afghanistan results since 2019 were taken from ESPNcricinfo's public scorecards.

## Licence

MIT. See [LICENSE](LICENSE).