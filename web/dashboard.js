// Renders dashboard.html from data/dashboard.json (written by `cwc27 export-web`).
import {
  byLatestRating,
  daysBetween,
  extendTo,
  favourite,
  percent,
  ratingDomain,
  scale,
  shortDate,
  stepPath,
  toggleHighlight,
} from "./dashboard-data.js";

const DATA_URL = "data/dashboard.json";
const STAGE_KEYS = ["group_stage", "super7", "semi_final", "final"];
const CHART_MARGIN = { top: 12, right: 12, bottom: 28, left: 44 };
const RATING_STEP = 50;
const SVG_NS = "http://www.w3.org/2000/svg";

const byId = (id) => document.getElementById(id);

function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === "text") node.textContent = value;
    else node.setAttribute(key, value);
  }
  node.append(...children);
  return node;
}

function svgEl(tag, attrs = {}) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
  return node;
}

function todayIso() {
  return new Date().toISOString().slice(0, 10);
}

function renderHero(data) {
  byId("days-left").textContent = String(Math.max(daysBetween(todayIso(), data.worldcup.start), 0));
  byId("favourite").textContent = data.worldcup.teams[0]?.name ?? "-";
  byId("updated").textContent =
    `Ratings include every result up to ${shortDate(data.ratings_through)}. ` +
    "Updated automatically each day.";
}

// Bars are drawn against the favourite, so the gaps between teams are easy to see.
function oddsRow(team, top) {
  const viaQualifier = team.group_stage < 1;
  const name = el("td", { class: "team" }, [team.name]);
  if (viaQualifier) name.append(el("span", { class: "qualifier-tag", text: "via Qualifier" }));
  const stages = STAGE_KEYS.map((key) => el("td", { class: "stage", text: percent(team[key]) }));
  const fill = el("span", { class: "bar-fill" });
  fill.style.width = `${((team.champion / top) * 100).toFixed(1)}%`;
  const bar = el("div", { class: "bar" }, [
    el("span", { class: "bar-track" }, [fill]),
    el("span", { class: "bar-value", text: percent(team.champion, 1) }),
  ]);
  return el("tr", {}, [name, ...stages, el("td", { class: "champion" }, [bar])]);
}

function renderOdds(worldcup) {
  byId("odds-note").textContent =
    `10,000 simulated tournaments. Ratings are blurred by about ${Math.round(worldcup.rating_sd)} ` +
    `Elo points, because the World Cup is ${worldcup.days_ahead} days after the latest result.`;
  const top = Math.max(...worldcup.teams.map((team) => team.champion), Number.EPSILON);
  byId("odds-body").replaceChildren(...worldcup.teams.map((team) => oddsRow(team, top)));
}

function fixtureItem(match) {
  const pA = percent(match.p_team_a);
  const pB = percent(1 - match.p_team_a);
  const share = el("span", { class: "split-a" });
  share.style.width = `${(match.p_team_a * 100).toFixed(1)}%`;
  const meta = el("div", { class: "fixture-meta" }, [
    el("span", { text: shortDate(match.date) }),
    el("span", { text: `${match.series}, match ${match.match_no}` }),
    el("span", { text: match.home ? `${match.home} at home` : "Neutral venue" }),
  ]);
  if (match.locked) meta.append(el("span", { class: "tag tag-locked", text: "Locked" }));
  const label = `${match.team_a} ${pA}, ${match.team_b} ${pB}`;
  return el("li", { class: "fixture" }, [
    meta,
    el("div", { class: "split-labels" }, [
      el("span", { text: `${match.team_a} ${pA}` }),
      el("span", { text: `${pB} ${match.team_b}` }),
    ]),
    el("div", { class: "split", role: "img", "aria-label": label }, [share]),
  ]);
}

function renderFixtures(upcoming) {
  const list = byId("fixtures");
  if (!upcoming.length) {
    list.replaceChildren(el("li", { class: "empty", text: "No fixtures are scheduled yet." }));
    return;
  }
  list.replaceChildren(...upcoming.map(fixtureItem));
}

function renderChips(order, highlighted, onToggle) {
  const chips = order.map(({ name }) => {
    const slot = highlighted.indexOf(name);
    const chip = el("button", {
      type: "button",
      class: "chip",
      "aria-pressed": String(slot >= 0),
      text: name,
    });
    if (slot >= 0) chip.dataset.slot = String(slot);
    chip.addEventListener("click", () => onToggle(name));
    return chip;
  });
  byId("chips").replaceChildren(...chips);
}

function yearTicks(startMs, endMs) {
  const ticks = [];
  for (let year = new Date(startMs).getUTCFullYear() + 1; ; year += 1) {
    const ms = Date.UTC(year, 0, 1);
    if (ms > endMs) return ticks;
    ticks.push({ ms, label: String(year) });
  }
}

function axisLabel(x, y, anchor, text) {
  const label = svgEl("text", { class: "axis-label", x, y, "text-anchor": anchor });
  label.textContent = text;
  return label;
}

function drawAxes(svg, x, y, [low, high], width, startMs, endMs) {
  for (let rating = low; rating <= high; rating += RATING_STEP) {
    const right = width - CHART_MARGIN.right;
    svg.append(
      svgEl("line", { class: "gridline", x1: CHART_MARGIN.left, x2: right, y1: y(rating), y2: y(rating) }),
      axisLabel(CHART_MARGIN.left - 8, y(rating) + 4, "end", String(rating)),
    );
  }
  for (const tick of yearTicks(startMs, endMs)) {
    svg.append(axisLabel(x(tick.ms), y(low) + 20, "middle", tick.label));
  }
}

function legendItem(name, points, since) {
  const latest = points[points.length - 1][1];
  const change = latest - points[0][1];
  const sign = change >= 0 ? "+" : "";
  return el("span", {}, [
    el("strong", { text: name }),
    ` ${Math.round(latest)} now, ${sign}${Math.round(change)} since ${shortDate(since)}`,
  ]);
}

function renderChart(timeline, through, highlighted) {
  const svg = byId("ratings-chart");
  const width = svg.clientWidth || 800;
  const height = svg.clientHeight || 360;
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  const series = Object.fromEntries(
    Object.entries(timeline.teams).map(([name, points]) => [name, extendTo(points, through)]),
  );
  const domain = ratingDomain(Object.values(series), RATING_STEP);
  const startMs = Date.parse(timeline.since);
  const endMs = Date.parse(through);
  const x = scale(startMs, endMs, CHART_MARGIN.left, width - CHART_MARGIN.right);
  const y = scale(domain[0], domain[1], height - CHART_MARGIN.bottom, CHART_MARGIN.top);
  svg.replaceChildren();
  drawAxes(svg, x, y, domain, width, startMs, endMs);
  const background = Object.keys(series).filter((name) => !highlighted.includes(name));
  for (const name of [...background, ...highlighted]) {
    const slot = highlighted.indexOf(name);
    const className = slot >= 0 ? `line line-${slot}` : "line";
    const path = svgEl("path", { class: className, d: stepPath(series[name], x, y) });
    const title = svgEl("title");
    title.textContent = name;
    path.append(title);
    svg.append(path);
  }
  byId("legend").replaceChildren(
    ...highlighted.map((name) => legendItem(name, series[name], timeline.since)),
  );
}

function renderRatings(timeline, through) {
  const order = byLatestRating(timeline.teams);
  let highlighted = order.slice(0, 2).map((team) => team.name);
  const draw = () => {
    renderChips(order, highlighted, (name) => {
      highlighted = toggleHighlight(highlighted, name);
      draw();
    });
    renderChart(timeline, through, highlighted);
  };
  draw();
  const chart = byId("ratings-chart");
  new ResizeObserver(() => renderChart(timeline, through, highlighted)).observe(chart);
}

function stat(value, label) {
  return el("p", { class: "stat" }, [
    el("span", { class: "stat-value", text: value }),
    el("span", { class: "stat-label", text: label }),
  ]);
}

function resultItem(result) {
  const call = favourite(result);
  const hit = call.team === result.winner;
  const outcome =
    result.winner == null
      ? el("span", { class: "result-call", text: "No result" })
      : el("span", { class: hit ? "result-hit" : "result-miss", text: hit ? "Called it" : "Missed" });
  const detail = `Favourite ${call.team} at ${percent(call.p)}. Winner: ${result.winner ?? "none"}`;
  return el("li", { class: "result" }, [
    el("span", { text: `${shortDate(result.date)}: ${result.team_a} v ${result.team_b}` }),
    outcome,
    el("span", { class: "result-call", text: detail }),
  ]);
}

function recordSummary(record) {
  const calibration = record.calibration.map((b) =>
    el("li", {
      text: `Favourites at ${percent(b.lower)} to ${percent(b.upper)}: won ${percent(b.observed_rate)} of ${b.count}`,
    }),
  );
  return [
    el("div", { class: "stats" }, [
      stat(String(record.matches), "matches scored"),
      stat(record.brier.toFixed(3), "Brier score"),
      stat(percent(record.accuracy), "favourites won"),
      stat(record.log_loss.toFixed(3), "log loss"),
    ]),
    el("ul", { class: "panel-note" }, calibration),
  ];
}

function renderRecord(record, results) {
  const empty = el("p", {
    class: "empty",
    text: "No predictions have been scored yet. The first come in after the next locked match is played.",
  });
  byId("record-body").replaceChildren(...(record ? recordSummary(record) : [empty]));
  byId("results").replaceChildren(...results.map(resultItem));
}

async function main() {
  try {
    const response = await fetch(DATA_URL, { cache: "no-cache" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    renderHero(data);
    renderOdds(data.worldcup);
    renderFixtures(data.upcoming);
    renderRatings(data.timeline, data.ratings_through);
    renderRecord(data.track_record, data.results);
  } catch (error) {
    byId("load-error").hidden = false;
    byId("updated").textContent = "";
    throw error;
  }
}

main();
