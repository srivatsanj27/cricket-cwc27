# cricket-cwc27

A data-driven predictor for men's ODI cricket in the build-up to the ICC Cricket World Cup 2027 (South Africa, Zimbabwe and Namibia, Oct–Nov 2027).

It tracks every men's ODI since the 2023 World Cup final and updates after each match to predict:

- **Squads**: the likely World Cup 15 for each nation
- **Matches**: win probabilities for upcoming ODIs and series
- **The World Cup**: each team's chance of reaching every stage and winning the title

Predictions are logged before each match and scored afterwards, so the model's track record is public.

> Status: early development.

## Website

`web/` is a fantasy bilateral series simulator built on the same ratings. See [web/README.md](web/README.md).

## Data

Ball-by-ball match data comes from [Cricsheet](https://cricsheet.org), which is openly licensed. Raw data is downloaded by the pipeline and not stored in this repository.

## Licence

MIT. See [LICENSE](LICENSE).
