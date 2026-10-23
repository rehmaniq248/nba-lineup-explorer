import { LineupSummary } from './lineup.models';

export const lineupKey = (lineup: LineupSummary): string => lineup.player_ids.join('|');

export const num = (lineup: LineupSummary, key: string): number => Number(lineup[key] ?? 0);

export const pct = (value: number, digits = 1): string => `${(value * 100).toFixed(digits)}%`;

export const signed = (value: number, digits = 1): string => `${value > 0 ? '+' : ''}${value.toFixed(digits)}`;

export const initials = (name: string): string =>
  name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0].toUpperCase())
    .join('');

// Diverging NBA scale: red (worst) through a neutral grey to blue (best). The ends are mid-tone so marks read on
// both the black and the white theme.
const SCALE_BAD = [217, 35, 63];
const SCALE_MID = [138, 138, 146];
const SCALE_GOOD = [47, 98, 201];

/**
 * Red → grey → blue scale. `t` runs from -1 (worst) to 1 (best); values outside are clamped.
 * Shared by the shot chart, the net-rating bars and the quadrant bubbles so a colour always means the same thing.
 */
export function scaleColor(t: number): string {
  const clamped = Math.max(-1, Math.min(1, t));
  const end = clamped < 0 ? SCALE_BAD : SCALE_GOOD;
  const weight = Math.abs(clamped);
  const channel = (index: number) => Math.round(SCALE_MID[index] + (end[index] - SCALE_MID[index]) * weight);
  return `rgb(${channel(0)}, ${channel(1)}, ${channel(2)})`;
}

/** Inches as feet and inches, e.g. 79 → 6'7". */
export const feetInches = (inches: number | null | undefined): string =>
  inches ? `${Math.floor(inches / 12)}'${Math.round(inches % 12)}"` : '—';

/** Display name for a "YYYY-MM" month. */
export const monthLabel = (month: string): string =>
  new Date(`${month}-01T12:00:00`).toLocaleString('en-US', { month: 'short' });
