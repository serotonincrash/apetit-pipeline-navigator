const cache = new Map<string, string>();

/** A colour from the theme in index.css, so charts and the rest of the app use the same values. */
export function themeColour(token: string): string {
  const known = cache.get(token);
  if (known) return known;
  const value = getComputedStyle(document.documentElement)
    .getPropertyValue(`--color-${token}`)
    .trim();
  cache.set(token, value);
  return value;
}

/** The fixed colour of a climate scenario. Past weather and today share the neutral grey. */
export function scenarioColour(scenario: string): string {
  return themeColour(scenario.startsWith("ssp") ? scenario : "today");
}
