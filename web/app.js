// Page controller: loads ratings, renders the builder and the series forecast.

import { matchProbability, simulateSeries } from "./sim.js";
import { MAX_MATCHES, MIN_MATCHES, defaultState, parseHash, resizeVenues, toHash } from "./state.js";

const DATA_URL = "data/ratings.json";
const N_SIMS = 20000;
const SEED = 27;
const NEUTRAL_LABEL = "Neutral venue";

const $ = (id) => document.getElementById(id);
const el = (tag, props = {}, children = []) => {
  const node = Object.assign(document.createElement(tag), props);
  node.append(...children);
  return node;
};

const percent = (p, digits = 0) => {
  if (p > 0 && p < 0.001) return "<0.1%";
  return `${(p * 100).toFixed(digits)}%`;
};

async function loadData() {
  const response = await fetch(DATA_URL, { cache: "no-cache" });
  if (!response.ok) throw new Error(`${DATA_URL} returned ${response.status}`);
  const data = await response.json();
  if (!Array.isArray(data.teams) || data.teams.length < 2 || !Array.isArray(data.venues)) {
    throw new Error(`${DATA_URL} is missing teams or venues`);
  }
  const numbers = [data.elo?.home_advantage, data.elo?.scale, ...data.teams.map((t) => t.rating)];
  if (!numbers.every(Number.isFinite)) throw new Error(`${DATA_URL} has a rating that isn't a number`);
  return {
    teamNames: data.teams.map((t) => t.name),
    ratings: new Map(data.teams.map((t) => [t.name, t.rating])),
    venues: data.venues,
    countryOf: new Map(data.venues.map((v) => [v.city, v.country])),
    elo: data.elo,
    meta: data,
  };
}

// --- builder -----------------------------------------------------------------

function fillTeamSelect(select, teamNames) {
  select.replaceChildren(...teamNames.map((name) => el("option", { value: name, textContent: name })));
  select.disabled = false;
}

function venueOptions(venues) {
  const byCountry = new Map();
  for (const v of venues) byCountry.set(v.country, [...(byCountry.get(v.country) ?? []), v]);
  const groups = [...byCountry].map(([country, cities]) =>
    el("optgroup", { label: country }, cities.map((v) => el("option", { value: v.city, textContent: v.city }))),
  );
  return [el("option", { value: "", textContent: NEUTRAL_LABEL }), ...groups];
}

function renderChips(state, onPick) {
  const chips = [];
  for (let n = MIN_MATCHES; n <= MAX_MATCHES; n += 1) {
    const chip = el("button", { type: "button", id: `count-${n}`, className: "chip", textContent: String(n) });
    chip.setAttribute("aria-pressed", String(n === state.venues.length));
    chip.setAttribute("aria-label", `${n} ${n === 1 ? "match" : "matches"}`);
    chip.addEventListener("click", () => onPick(n));
    chips.push(chip);
  }
  $("count-chips").replaceChildren(...chips);
}

function venueContext(state, country) {
  if (country === state.a) return `${state.a} at home`;
  if (country === state.b) return `${state.b} at home`;
  return country ? `Neutral, in ${country}` : "Neutral";
}

function renderFixtures(state, data, probabilities, onVenue) {
  const optionsTemplate = el("select", {}, venueOptions(data.venues));
  const rows = state.venues.map((city, i) => {
    const id = `venue-${i + 1}`;
    const select = optionsTemplate.cloneNode(true);
    Object.assign(select, { id, value: city });
    select.addEventListener("change", () => onVenue(i, select.value));

    const p = probabilities[i];
    const favourite = p >= 0.5 ? state.a : state.b;
    const odds = el("div", { className: "fixture-odds" }, [
      el("strong", { textContent: `${favourite} ${percent(Math.max(p, 1 - p))}` }),
      el("span", { textContent: venueContext(state, data.countryOf.get(city) ?? null) }),
    ]);
    return el("li", { className: "fixture" }, [
      el("label", { className: "fixture-no", htmlFor: id, textContent: `ODI ${i + 1}` }),
      el("div", { className: "select" }, [select]),
      odds,
    ]);
  });
  $("fixtures").replaceChildren(...rows);
}

// --- result ------------------------------------------------------------------

function verdictRow(className, label, value) {
  return el("div", { className: `verdict-row ${className}` }, [
    el("dt", { textContent: label }),
    el("dd", { textContent: value }),
  ]);
}

function splitBar(state, forecast) {
  const bar = el("div", { className: "split", role: "img" });
  bar.setAttribute(
    "aria-label",
    `${state.a} ${percent(forecast.pA)}, drawn ${percent(forecast.pDraw)}, ${state.b} ${percent(forecast.pB)}`,
  );
  for (const [cls, p] of [["a", forecast.pA], ["draw", forecast.pDraw], ["b", forecast.pB]]) {
    if (p > 0) bar.append(el("span", { className: cls, style: `flex-basis: ${p * 100}%` }));
  }
  return bar;
}

function scorelineRows(state, forecast) {
  const top = Math.max(...forecast.scorelines.map((s) => s.p)) || 1;
  return forecast.scorelines.filter((s) => s.p > 0).map(({ a, b, p }) => {
    const side = a > b ? "for-a" : b > a ? "for-b" : "for-none";
    const label = a > b ? `${state.a} ${a}-${b}` : b > a ? `${state.b} ${b}-${a}` : `Drawn ${a}-${b}`;
    const bar = el("span", { className: "scoreline-bar", style: `transform: scaleX(${p / top})` });
    return el("li", { className: `scoreline ${side}` }, [
      el("span", { className: "scoreline-label", textContent: label, title: label }),
      bar,
      el("span", { className: "scoreline-value", textContent: percent(p, 1) }),
    ]);
  });
}

function renderResult(state, data, forecast) {
  const n = forecast.nMatches;
  const rows = [verdictRow("team-a", state.a, percent(forecast.pA)), verdictRow("team-b", state.b, percent(forecast.pB))];
  if (n % 2 === 0) rows.push(verdictRow("drawn", "Series drawn", percent(forecast.pDraw)));

  const result = $("result");
  result.replaceChildren(
    el("h2", { className: "result-heading", textContent: `Chance of winning the ${n}-match series` }),
    el("dl", { className: "verdict" }, rows),
    splitBar(state, forecast),
    el("h2", { className: "result-heading", textContent: "Final scoreline" }),
    el("ol", { className: "scorelines" }, scorelineRows(state, forecast)),
    el("p", {
      className: "result-note",
      textContent: `Ratings: ${state.a} ${Math.round(data.ratings.get(state.a))}, ${state.b} ${Math.round(data.ratings.get(state.b))}.`,
    }),
  );
  result.setAttribute("aria-busy", "false");
  const drawn = n % 2 === 0 ? `, drawn ${percent(forecast.pDraw)}` : "";
  $("summary").textContent = `${state.a} ${percent(forecast.pA)}, ${state.b} ${percent(forecast.pB)}${drawn}.`;
  result.classList.remove("updated");
  void result.offsetWidth; // restart the fade
  result.classList.add("updated");
}

function renderError(message) {
  const result = $("result");
  result.setAttribute("aria-busy", "false");
  result.replaceChildren(
    el("div", { className: "result-error" }, [
      el("h2", { textContent: "Ratings didn't load" }),
      el("p", { textContent: message }),
    ]),
  );
  $("fixtures").replaceChildren();
  $("data-note").textContent = "No ratings loaded.";
}

function renderMeta(data) {
  const through = new Date(`${data.meta.ratings_through}T00:00:00Z`).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
  $("data-note").textContent = `Ratings through ${through}, from ${data.meta.matches_rated.toLocaleString("en-GB")} ODIs.`;
  for (const node of document.querySelectorAll('[data-fill="home-advantage"]')) {
    node.textContent = String(data.elo.home_advantage);
  }
}

// --- wiring ------------------------------------------------------------------

function start(data) {
  const cities = new Set(data.venues.map((v) => v.city));
  let state = parseHash(location.hash, data.teamNames, cities) ?? defaultState(data.teamNames, data.venues);
  const teamA = $("team-a");
  const teamB = $("team-b");
  fillTeamSelect(teamA, data.teamNames);
  fillTeamSelect(teamB, data.teamNames);

  const update = (next) => {
    state = next;
    render();
  };

  const pickTeam = (side, name) => {
    const other = side === "a" ? "b" : "a";
    // Picking the team already on the other side swaps them, so A and B never match.
    const next = state[other] === name ? { ...state, [side]: name, [other]: state[side] } : { ...state, [side]: name };
    update(next);
  };

  function render() {
    const focusedId = document.activeElement?.id;
    teamA.value = state.a;
    teamB.value = state.b;
    const probabilities = state.venues.map((city) =>
      matchProbability(state.a, state.b, data.countryOf.get(city) ?? null, data.ratings, data.elo),
    );
    renderChips(state, (n) => update({ ...state, venues: resizeVenues(state.venues, n) }));
    renderFixtures(state, data, probabilities, (i, city) =>
      update({ ...state, venues: state.venues.map((v, j) => (j === i ? city : v)) }),
    );
    renderResult(state, data, simulateSeries(probabilities, N_SIMS, SEED));
    history.replaceState(null, "", toHash(state));
    if (focusedId) $(focusedId)?.focus(); // rebuilt controls would otherwise drop keyboard focus
  }

  teamA.addEventListener("change", () => pickTeam("a", teamA.value));
  teamB.addEventListener("change", () => pickTeam("b", teamB.value));
  $("swap").addEventListener("click", () => update({ ...state, a: state.b, b: state.a }));
  $("swap").disabled = false;
  // A pasted share link only changes the hash, which doesn't reload the page.
  window.addEventListener("hashchange", () => {
    const linked = parseHash(location.hash, data.teamNames, cities);
    if (linked) update(linked);
  });
  renderMeta(data);
  render();
}

loadData().then(
  (data) => {
    try {
      start(data);
    } catch (error) {
      console.error("The simulator failed while starting:", error);
      renderError("Something went wrong running the simulation. Try a different series or refresh the page.");
    }
  },
  (error) => {
    console.error("Could not load ratings:", error);
    renderError("Refresh the page to try again. If it keeps happening, the ratings file may be missing.");
  },
);
