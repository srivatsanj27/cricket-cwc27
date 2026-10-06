# cricket-cwc27

A data-driven predictor for men's ODI cricket in the build-up to the ICC Cricket World Cup 2027 (South Africa, Zimbabwe and Namibia, Oct–Nov 2027).

It tracks every men's ODI since the 2023 World Cup final and updates after each match to predict:

- **Matches**: win probabilities for upcoming ODIs and series (working now)
- **Squads**: the likely World Cup 15 for each nation (planned)
- **The World Cup**: each team's chance of reaching every stage and winning the title (planned)

Predictions are logged before each match and scored afterwards, so the model's track record is public.

## Quick links

| What | Where |
|---|---|
| Fantasy series website (local) | http://localhost:8027, after starting the server below |
| Live predictions log | [data/predictions_log.csv](data/predictions_log.csv) |
| Upcoming fixtures | [data/fixtures.csv](data/fixtures.csv) |
| Results entered by hand | [data/manual/](data/manual/) |
| Website details | [web/README.md](web/README.md) |

Start the website:

```bash
python3 -m http.server 8027 --directory web
```

Then open http://localhost:8027. Pick two teams, 1 to 7 ODIs and a venue for each match, and it plays the series 20,000 times. The URL updates as you go, so you can bookmark or share a series.

## What works so far

- **Data:** every men's ODI since 2019 from Cricsheet, plus hand-entered results where Cricsheet is missing matches (Afghanistan since Nov 2024, and recent games it hasn't published yet). Stored in DuckDB.
- **Ratings:** team Elo ratings with a home advantage. Tuned settings are K = 25 and home advantage = 80 points.
- **Backtest:** walk-forward scoring (each match predicted only from earlier results) against a coin flip and a win-rate baseline. Since the 2023 World Cup final, Elo scores a Brier of 0.224, against about 0.241 for win rate and 0.247 for a coin flip (lower is better).
- **Series:** Monte Carlo simulation of bilateral series (chance of each scoreline and of winning the series).
- **Live loop:** fixtures, a prediction log that locks each prediction the day before the match and scores it afterwards, and one command to refresh everything.
- **Website:** the fantasy series simulator in `web/`.

## Next

- Tri-series simulator (round robin plus final), in time for the Pakistan tri-series from 18 Oct 2026
- Phase 2: player ratings and likely World Cup squads
- Phase 3: World Cup 2027 simulation
- Phase 4: scheduled updates and a public dashboard

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
| `cwc27 export-web` | Write the latest ratings to `web/data/ratings.json` for the website |
| `cwc27 backtest [--k K] [--home-advantage H]` | Score Elo and the baselines on past ODIs |
| `cwc27 tune` | Grid-search Elo settings and confirm them on recent matches |

### After each match

```bash
cwc27 result 2026-10-18 Pakistan "Sri Lanka" --winner Pakistan --runs 25
```

```bash
cwc27 update
```

```bash
cwc27 export-web
```

Then commit the updated `data/` and `web/data/ratings.json`.

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
  ingest/       Cricsheet and manual-results loaders
  ratings/      Elo engine and model wrapper
  evaluation/   backtest, metrics, baselines, tuning
  simulate/     series simulation and outlooks
  tracking/     prediction log and the update loop
  web_export.py ratings JSON for the website
  cli.py        the cwc27 command
config/         city to country lookup for home advantage
data/           fixtures, manual results, prediction log (raw data and database are not committed)
web/            fantasy series website (static HTML, CSS and JavaScript)
tests/          pytest suite
```

## Data

Ball-by-ball match data comes from [Cricsheet](https://cricsheet.org), which is openly licensed. Raw data is downloaded by the pipeline and not stored in this repository.

## Licence

MIT. See [LICENSE](LICENSE).
