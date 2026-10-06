// Page state ({a, b, venues}) and its shareable URL hash. Pure functions only.

export const MIN_MATCHES = 1;
export const MAX_MATCHES = 7;
export const DEFAULT_MATCHES = 3;
const VENUE_SEPARATOR = "|";
const NEUTRAL = "";

/** Top two teams, three matches at team A's home grounds (or neutral if it has none). */
export function defaultState(teamNames, venues) {
  const [a, b] = teamNames;
  const homeGrounds = venues.filter((v) => v.country === a).map((v) => v.city);
  const pick = (i) => (homeGrounds.length ? homeGrounds[i % homeGrounds.length] : NEUTRAL);
  return { a, b, venues: Array.from({ length: DEFAULT_MATCHES }, (_, i) => pick(i)) };
}

export function toHash(state) {
  const params = new URLSearchParams({
    a: state.a,
    b: state.b,
    v: state.venues.join(VENUE_SEPARATOR),
  });
  return `#${params}`;
}

/** State from a URL hash, or null if it is missing or names anything we don't know. */
export function parseHash(hash, teamNames, cityNames) {
  const params = new URLSearchParams(hash.replace(/^#/, ""));
  const a = params.get("a");
  const b = params.get("b");
  const v = params.get("v");
  if (a === null || b === null || v === null) return null;

  const teams = new Set(teamNames);
  if (!teams.has(a) || !teams.has(b) || a === b) return null;

  const venues = v.split(VENUE_SEPARATOR);
  if (venues.length < MIN_MATCHES || venues.length > MAX_MATCHES) return null;
  if (venues.some((city) => city !== NEUTRAL && !cityNames.has(city))) return null;
  return { a, b, venues };
}

/** A new venue list of length n; added matches repeat the last venue. */
export function resizeVenues(venues, n) {
  const last = venues.at(-1) ?? NEUTRAL;
  return Array.from({ length: n }, (_, i) => (i < venues.length ? venues[i] : last));
}
