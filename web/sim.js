// Series simulation for the browser. Mirrors cwc27.ratings.elo.win_probability and
// cwc27.simulate.series.simulate_series so the site agrees with the Python model.

/** Probability that A beats B: 1 / (1 + 10 ** ((rb - ra) / scale)). */
export function expectedScore(ratingA, ratingB, scale) {
  return 1 / (1 + 10 ** ((ratingB - ratingA) / scale));
}

/** "a" or "b" if that team is playing in its own country, otherwise null (neutral). */
export function homeSide(teamA, teamB, venueCountry) {
  if (venueCountry === teamA) return "a";
  if (venueCountry === teamB) return "b";
  return null;
}

/** Chance that teamA wins one match played in `venueCountry` (null for neutral). */
export function matchProbability(teamA, teamB, venueCountry, ratings, elo) {
  if (teamA === teamB) throw new Error(`A team cannot play itself: ${teamA}`);
  for (const team of [teamA, teamB]) {
    if (!ratings.has(team)) throw new Error(`No rating for ${team}`);
  }
  const home = homeSide(teamA, teamB, venueCountry);
  const ratingA = ratings.get(teamA) + (home === "a" ? elo.home_advantage : 0);
  const ratingB = ratings.get(teamB) + (home === "b" ? elo.home_advantage : 0);
  return expectedScore(ratingA, ratingB, elo.scale);
}

/** Small seeded random number generator (mulberry32), so a seed always gives the same run. */
function seededRandom(seed) {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/**
 * Play the series `nSims` times. `probabilities[i]` is A's chance in match i.
 * Every match is played and has a winner. Returns every possible scoreline, A's best first.
 */
export function simulateSeries(probabilities, nSims, seed) {
  if (probabilities.length === 0) throw new Error("No matches to simulate");
  if (probabilities.some((p) => !(p >= 0 && p <= 1))) {
    throw new Error("Match probabilities must be between 0 and 1");
  }
  if (!(nSims >= 1)) throw new Error("Must simulate at least one series");

  const n = probabilities.length;
  const counts = new Array(n + 1).fill(0); // counts[k] = series where A won k matches
  const random = seededRandom(seed);
  for (let sim = 0; sim < nSims; sim += 1) {
    let aWins = 0;
    for (const p of probabilities) {
      if (random() < p) aWins += 1;
    }
    counts[aWins] += 1;
  }

  const scorelines = counts
    .map((count, a) => ({ a, b: n - a, p: count / nSims }))
    .reverse();
  const share = (keep) => scorelines.filter(keep).reduce((sum, s) => sum + s.p, 0);
  return {
    nMatches: n,
    scorelines,
    pA: share((s) => s.a > s.b),
    pB: share((s) => s.b > s.a),
    pDraw: share((s) => s.a === s.b),
  };
}
