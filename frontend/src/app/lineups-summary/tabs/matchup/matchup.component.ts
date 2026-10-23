import { Component, computed, inject } from '@angular/core';

import { num } from '../../../_services/lineup.utils';
import { LineupsStore } from '../../../_services/lineups.store';
import { LineupHeaderComponent } from '../../shared/lineup-header/lineup-header.component';
import { SplitBarsComponent, SplitRow } from '../../shared/split-bars/split-bars.component';

const APPROX_FALLBACK = 'Approximation, estimated from the play-by-play.';

interface Slice {
  label: string;
  lineup: number;
  opponent: number;
  color: string;
}

@Component({
  selector: 'matchup-tab',
  imports: [LineupHeaderComponent, SplitBarsComponent],
  templateUrl: './matchup.component.html',
  styleUrl: './matchup.component.scss',
})
export class MatchupComponent {
  readonly store = inject(LineupsStore);

  readonly rows = computed<SplitRow[]>(() => {
    const l = this.store.selected();
    if (!l) {
      return [];
    }
    return [
      { label: 'Points per possession', left: num(l, 'offensive_ppp'), right: num(l, 'defensive_ppp'), format: 'ppp' },
      { label: 'Effective FG%', left: num(l, 'offensive_efg_pct'), right: num(l, 'defensive_efg_pct'), format: 'pct' },
      { label: 'True shooting %', left: num(l, 'offensive_ts_pct'), right: num(l, 'defensive_ts_pct'), format: 'pct' },
      { label: 'Turnover rate', left: num(l, 'offensive_turnover_rate'), right: num(l, 'defensive_turnover_rate'), format: 'pct', lowerWins: true },
      { label: 'Free-throw rate', left: num(l, 'offensive_ft_rate'), right: num(l, 'defensive_ft_rate'), format: 'pct' },
      { label: 'Offensive rebound %', left: num(l, 'oreb_pct'), right: num(l, 'opponent_oreb_pct'), format: 'pct' },
    ];
  });

  /** How the points were created, per 100 possessions: in the paint, in transition, off misses, off turnovers. */
  readonly context = computed<SplitRow[]>(() => {
    const l = this.store.selected();
    if (!l) {
      return [];
    }
    // split-bars' per100 format multiplies by 100, so the API's per-100 values are passed per possession.
    const per = (side: 'offensive' | 'defensive', stat: string) => num(l, `${side}_${stat}_per100`) / 100;
    return [
      { label: 'Paint points', left: per('offensive', 'paint_points'), right: per('defensive', 'paint_points'), format: 'per100' },
      { label: 'Fast-break points', left: per('offensive', 'fastbreak_points'), right: per('defensive', 'fastbreak_points'), format: 'per100' },
      { label: 'Second-chance points', left: per('offensive', 'second_chance_points'), right: per('defensive', 'second_chance_points'), format: 'per100' },
      { label: 'Points off turnovers', left: per('offensive', 'points_off_turnovers'), right: per('defensive', 'points_off_turnovers'), format: 'per100' },
    ];
  });

  /**
   * Shot value from the two approximated stats: points per shot attempt (field goals plus and-ones, with each
   * trip to the line as one attempt) and free throws drawn per 100 possessions.
   */
  readonly shotValue = computed<SplitRow[]>(() => {
    const l = this.store.selected();
    const approximations = this.store.meta()?.approximations ?? {};
    if (!l) {
      return [];
    }
    const ratio = (a: number, b: number) => (b ? a / b : 0);
    return [
      {
        label: 'Shot-attempt points per attempt',
        left: ratio(num(l, 'offensive_shot_attempt_points'), num(l, 'offensive_shot_attempts')),
        right: ratio(num(l, 'defensive_shot_attempt_points'), num(l, 'defensive_shot_attempts')),
        format: 'ppp',
        approx: approximations['shot_attempt_points'] ?? APPROX_FALLBACK,
      },
      {
        label: 'Free-throw potential points per 100',
        left: ratio(num(l, 'offensive_ft_potential_points'), num(l, 'offensive_possessions')),
        right: ratio(num(l, 'defensive_ft_potential_points'), num(l, 'defensive_possessions')),
        format: 'per100',
        approx: approximations['ft_potential_points'] ?? APPROX_FALLBACK,
      },
    ];
  });

  /** Where the points came from, for the lineup's offense and for opponents against it. */
  readonly slices = computed<Slice[]>(() => {
    const l = this.store.selected();
    if (!l) {
      return [];
    }
    return [
      { label: '2-point field goals', lineup: num(l, 'offensive_fg2_made') * 2, opponent: num(l, 'defensive_fg2_made') * 2, color: 'var(--lineup)' },
      { label: '3-point field goals', lineup: num(l, 'offensive_fg3_made') * 3, opponent: num(l, 'defensive_fg3_made') * 3, color: 'var(--text)' },
      { label: 'Free throws', lineup: num(l, 'offensive_ft_made'), opponent: num(l, 'defensive_ft_made'), color: 'var(--opponent)' },
    ];
  });

  readonly mix = computed(() => {
    const slices = this.slices();
    const build = (pick: (slice: Slice) => number) => {
      const total = slices.reduce((sum, slice) => sum + pick(slice), 0);
      return {
        total,
        parts: slices.map((slice) => ({ ...slice, value: pick(slice), share: total ? (pick(slice) / total) * 100 : 0 })),
      };
    };
    return { lineup: build((slice) => slice.lineup), opponent: build((slice) => slice.opponent) };
  });
}
