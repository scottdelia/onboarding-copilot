/**
 * Colour-scheme preference.
 *
 * Lifted from the Underwriting Copilot, minus the rate-class helpers — those
 * depend on that project's canonical ladder and have no meaning here. This site
 * sets `--tier` directly, because a verdict badge and an ROI input tag borrow
 * the ladder's hues without belonging to the ladder.
 *
 * Three states, not two: light, dark, and "whatever the system says". The third
 * is the default and the one most readers will never change, so it has to be the
 * state the page renders in before any script runs.
 */

export type ColorScheme = 'light' | 'dark' | 'system';

/**
 * Shared with the Underwriting Copilot on purpose.
 *
 * The two sites are different origins, so this does not actually share storage
 * between them — but keeping the key identical means the inline pre-paint script
 * in each `index.html` is the same three lines, and a reader who later opens
 * both from one host gets one preference rather than two.
 */
const STORAGE_KEY = 'uc-color-scheme';

/** Read the stored preference. `system` when nothing was chosen. */
export function readColorScheme(): ColorScheme {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    return stored === 'light' || stored === 'dark' ? stored : 'system';
  } catch {
    // Storage can throw in a locked-down context. A theme preference is not
    // worth failing the page over.
    return 'system';
  }
}

/**
 * Apply a scheme by stamping `data-theme` on the document element.
 *
 * `system` removes the attribute rather than computing a value, which hands the
 * decision back to the `prefers-color-scheme` media query in index.css. That
 * matters for a reader who changes their OS theme with this page already open:
 * the page follows, because nothing here froze a value into the DOM.
 */
export function applyColorScheme(scheme: ColorScheme): void {
  const root = document.documentElement;
  if (scheme === 'system') {
    root.removeAttribute('data-theme');
  } else {
    root.setAttribute('data-theme', scheme);
  }
  try {
    if (scheme === 'system') {
      localStorage.removeItem(STORAGE_KEY);
    } else {
      localStorage.setItem(STORAGE_KEY, scheme);
    }
  } catch {
    // See readColorScheme.
  }
}
