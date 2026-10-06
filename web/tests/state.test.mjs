import assert from "node:assert/strict";
import { test } from "node:test";

import { MAX_MATCHES, defaultState, parseHash, resizeVenues, toHash } from "../state.js";

const TEAMS = ["India", "Australia", "Nepal"];
const VENUES = [
  { city: "Melbourne", country: "Australia" },
  { city: "Sydney", country: "Australia" },
  { city: "Chennai", country: "India" },
  { city: "Mumbai", country: "India" },
  { city: "Dubai", country: "United Arab Emirates" },
];
const CITIES = new Set(VENUES.map((v) => v.city));

test("default is the top two teams, three matches in team A's country", () => {
  assert.deepEqual(defaultState(TEAMS, VENUES), {
    a: "India",
    b: "Australia",
    venues: ["Chennai", "Mumbai", "Chennai"],
  });
});

test("default falls back to neutral venues when team A has no grounds", () => {
  assert.deepEqual(defaultState(["Nepal", "India"], VENUES).venues, ["", "", ""]);
});

test("hash round trip keeps teams, venues and neutral matches", () => {
  const state = { a: "Australia", b: "India", venues: ["Sydney", "", "Mumbai"] };
  assert.deepEqual(parseHash(toHash(state), TEAMS, CITIES), state);
});

test("hash with unknown or repeated teams is ignored", () => {
  assert.equal(parseHash("#a=India&b=Narnia&v=Mumbai", TEAMS, CITIES), null);
  assert.equal(parseHash("#a=India&b=India&v=Mumbai", TEAMS, CITIES), null);
});

test("hash with an unknown city or too many matches is ignored", () => {
  assert.equal(parseHash("#a=India&b=Nepal&v=Atlantis", TEAMS, CITIES), null);
  const tooMany = Array(MAX_MATCHES + 1).fill("Mumbai").join("|");
  assert.equal(parseHash(`#a=India&b=Nepal&v=${tooMany}`, TEAMS, CITIES), null);
});

test("empty or missing hash is ignored", () => {
  assert.equal(parseHash("", TEAMS, CITIES), null);
  assert.equal(parseHash("#method", TEAMS, CITIES), null);
});

test("resizing repeats the last venue and never changes the input", () => {
  const venues = ["Sydney", "Mumbai"];
  assert.deepEqual(resizeVenues(venues, 4), ["Sydney", "Mumbai", "Mumbai", "Mumbai"]);
  assert.deepEqual(resizeVenues(venues, 1), ["Sydney"]);
  assert.deepEqual(venues, ["Sydney", "Mumbai"]);
});
