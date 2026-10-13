import assert from "node:assert/strict";
import { test } from "node:test";

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
} from "../dashboard-data.js";

test("percent rounds, and shows tiny chances as under one percent", () => {
  assert.equal(percent(0.2022), "20%");
  assert.equal(percent(0.2022, 1), "20.2%");
  assert.equal(percent(0.001), "<1%");
  assert.equal(percent(0), "0%");
});

test("dates count whole days and print short", () => {
  assert.equal(daysBetween("2026-10-05", "2027-10-02"), 362);
  assert.equal(shortDate("2026-10-18"), "18 Oct 2026");
});

test("the favourite is whichever side has the higher chance", () => {
  const match = { team_a: "England", team_b: "Sri Lanka", p_team_a: 0.4912 };
  assert.deepEqual(favourite(match), { team: "Sri Lanka", p: 1 - 0.4912 });
});

test("scale maps a domain onto a range, including inverted ranges", () => {
  const y = scale(1400, 1700, 300, 0);
  assert.equal(y(1400), 300);
  assert.equal(y(1700), 0);
  assert.equal(scale(5, 5, 0, 10)(5), 0);
});

test("the rating domain rounds out to whole steps", () => {
  const series = [[["2024-01-01", 1523]], [["2024-01-01", 1648.2]]];
  assert.deepEqual(ratingDomain(series), [1500, 1650]);
});

test("step paths hold each rating until the next match", () => {
  const x = (t) => (t - Date.parse("2024-01-01")) / 86_400_000;
  const y = (r) => r - 1500;
  const path = stepPath(
    [
      ["2024-01-01", 1500],
      ["2024-01-03", 1510],
    ],
    x,
    y,
  );
  assert.equal(path, "M0.0,0.0 L2.0,0.0 L2.0,10.0");
});

test("series extend flat to the end date, once", () => {
  const points = [["2024-01-01", 1500]];
  assert.deepEqual(extendTo(points, "2024-02-01"), [
    ["2024-01-01", 1500],
    ["2024-02-01", 1500],
  ]);
  assert.equal(extendTo(points, "2024-01-01"), points);
});

test("at most two teams are highlighted, and a second pick removes one", () => {
  assert.deepEqual(toggleHighlight([], "India"), ["India"]);
  assert.deepEqual(toggleHighlight(["India", "England"], "Australia"), ["England", "Australia"]);
  assert.deepEqual(toggleHighlight(["India", "England"], "India"), ["England"]);
});

test("teams sort by their latest rating", () => {
  const teams = {
    England: [["2024-01-01", 1600], ["2026-01-01", 1520]],
    India: [["2026-01-01", 1650]],
  };
  assert.deepEqual(
    byLatestRating(teams).map((t) => t.name),
    ["India", "England"],
  );
});
