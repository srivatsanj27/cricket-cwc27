// Pure helpers for dashboard.html: formatting and chart geometry. No DOM access, so they
// can be tested with node --test (tests/dashboard.test.mjs).

export const DAY_MS = 24 * 60 * 60 * 1000;

export function percent(p, digits = 0) {
  if (p > 0 && p < 0.005 && digits === 0) return "<1%";
  return `${(p * 100).toFixed(digits)}%`;
}

export function daysBetween(fromIso, toIso) {
  return Math.round((Date.parse(toIso) - Date.parse(fromIso)) / DAY_MS);
}

export function shortDate(iso) {
  const [year, month, day] = iso.split("-").map(Number);
  const names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return `${day} ${names[month - 1]} ${year}`;
}

// The favourite and their chance, from team A's probability.
export function favourite(match) {
  return match.p_team_a >= 0.5
    ? { team: match.team_a, p: match.p_team_a }
    : { team: match.team_b, p: 1 - match.p_team_a };
}

// Linear scale from [d0, d1] onto [r0, r1].
export function scale(d0, d1, r0, r1) {
  const span = d1 - d0 || 1;
  return (value) => r0 + ((value - d0) / span) * (r1 - r0);
}

// Min and max rating across the given series, padded and rounded out to `step`.
export function ratingDomain(series, step = 50) {
  const values = series.flat().map((point) => point[1]);
  const low = Math.min(...values);
  const high = Math.max(...values);
  return [Math.floor(low / step) * step, Math.ceil(high / step) * step];
}

// An SVG path through [isoDate, rating] points, drawn as steps: a rating holds until the
// next match changes it.
export function stepPath(points, x, y) {
  return points
    .map(([iso, rating], i) => {
      const px = x(Date.parse(iso)).toFixed(1);
      const py = y(rating).toFixed(1);
      if (i === 0) return `M${px},${py}`;
      const prevY = y(points[i - 1][1]).toFixed(1);
      return `L${px},${prevY} L${px},${py}`;
    })
    .join(" ");
}

// Extend a series flat to `endIso`, so every line reaches the right edge of the chart.
export function extendTo(points, endIso) {
  if (!points.length || points[points.length - 1][0] >= endIso) return points;
  return [...points, [endIso, points[points.length - 1][1]]];
}

// Highlighted teams: keep at most two, newest choice last; picking a team again removes it.
export function toggleHighlight(current, team) {
  if (current.includes(team)) return current.filter((t) => t !== team);
  return [...current, team].slice(-2);
}

// Teams in order of their latest rating, best first.
export function byLatestRating(teams) {
  return Object.entries(teams)
    .map(([name, points]) => ({ name, rating: points[points.length - 1][1] }))
    .sort((a, b) => b.rating - a.rating);
}
