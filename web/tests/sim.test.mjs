import assert from "node:assert/strict";
import { test } from "node:test";

import { expectedScore, homeSide, matchProbability, simulateSeries } from "../sim.js";

const ELO = { home_advantage: 80, scale: 400 };
const RATINGS = new Map([["India", 1600], ["Australia", 1600], ["Nepal", 1200]]);

test("equal ratings give an even chance", () => {
  assert.equal(expectedScore(1500, 1500, 400), 0.5);
});

test("a 400 point gap gives ten to one odds", () => {
  assert.ok(Math.abs(expectedScore(1900, 1500, 400) - 10 / 11) < 1e-12);
});

test("home side is whichever team's country hosts the match", () => {
  assert.equal(homeSide("India", "Australia", "India"), "a");
  assert.equal(homeSide("India", "Australia", "Australia"), "b");
  assert.equal(homeSide("India", "Australia", "United Arab Emirates"), null);
  assert.equal(homeSide("India", "Australia", null), null);
});

test("match probability adds home advantage to the host", () => {
  const neutral = matchProbability("India", "Australia", null, RATINGS, ELO);
  const home = matchProbability("India", "Australia", "India", RATINGS, ELO);
  const away = matchProbability("India", "Australia", "Australia", RATINGS, ELO);
  assert.equal(neutral, 0.5);
  assert.ok(Math.abs(home - expectedScore(1680, 1600, 400)) < 1e-12);
  assert.ok(Math.abs(home + away - 1) < 1e-12);
});

test("match probability rejects a team playing itself or an unknown team", () => {
  assert.throws(() => matchProbability("India", "India", null, RATINGS, ELO), /itself/);
  assert.throws(() => matchProbability("India", "Narnia", null, RATINGS, ELO), /No rating/);
});

test("series outcomes cover every scoreline and add up to one", () => {
  const result = simulateSeries([0.6, 0.6, 0.6], 5000, 7);
  assert.equal(result.nMatches, 3);
  assert.deepEqual(result.scorelines.map((s) => [s.a, s.b]), [[3, 0], [2, 1], [1, 2], [0, 3]]);
  const total = result.scorelines.reduce((sum, s) => sum + s.p, 0);
  assert.ok(Math.abs(total - 1) < 1e-9);
  assert.ok(Math.abs(result.pA + result.pB + result.pDraw - 1) < 1e-9);
  assert.equal(result.pDraw, 0);
});

test("simulation is close to the exact answer", () => {
  // P(A wins best of 3 at p=0.6) = 0.6^3 + 3 * 0.6^2 * 0.4 = 0.648
  const result = simulateSeries([0.6, 0.6, 0.6], 40000, 1);
  assert.ok(Math.abs(result.pA - 0.648) < 0.01);
});

test("even series can be drawn", () => {
  const result = simulateSeries([0.5, 0.5], 20000, 3);
  assert.ok(Math.abs(result.pDraw - 0.5) < 0.02);
});

test("certain results give certain series", () => {
  const result = simulateSeries([1, 1, 0], 100, 9);
  assert.equal(result.pA, 1);
  assert.deepEqual(result.scorelines.find((s) => s.a === 2).p, 1);
});

test("same seed gives the same forecast", () => {
  assert.deepEqual(simulateSeries([0.55, 0.7], 1000, 42), simulateSeries([0.55, 0.7], 1000, 42));
});

test("simulateSeries validates its input", () => {
  assert.throws(() => simulateSeries([], 100, 1), /No matches/);
  assert.throws(() => simulateSeries([1.2], 100, 1), /between 0 and 1/);
  assert.throws(() => simulateSeries([0.5], 0, 1), /at least one/);
});
