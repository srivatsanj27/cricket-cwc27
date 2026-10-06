# Fantasy Series (web)

A static page: pick two teams, the number of ODIs and a venue for each, and see who wins
the series from 20,000 simulations. It runs entirely in the browser and has no build step.

## Update the ratings

After new results are in (`cwc27 update`), export them for the site:

```bash
cwc27 export-web
```

This writes `web/data/ratings.json`: Elo ratings for every team with an ODI since the 2023
World Cup final, the home advantage, and the city-to-country list used for venues. Commit it
alongside the site.

## Run locally

```bash
python3 -m http.server 8027 --directory web
```

Then open http://localhost:8027. Opening `index.html` as a file will not work, because the
page loads ES modules and JSON.

## Test

```bash
cd web && npm test
```

`sim.js` mirrors `cwc27.ratings.elo.win_probability` and `cwc27.simulate.series.simulate_series`;
`state.js` handles the shareable URL (`#a=India&b=Australia&v=Mumbai|Chennai|`, empty = neutral).

## Design

`DESIGN.md` holds the visual rules, adapted from the awesome-design-md Nike analysis with the
taste-skill guidelines. Project overrides are at the top of that file.
