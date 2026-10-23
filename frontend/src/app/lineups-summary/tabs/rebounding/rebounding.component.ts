import { Component, computed, inject } from '@angular/core';

import { LineupSummary } from '../../../_services/lineup.models';
import { feetInches, initials, lineupKey, num, pct, signed } from '../../../_services/lineup.utils';
import { LineupsStore } from '../../../_services/lineups.store';
import { LineupHeaderComponent } from '../../shared/lineup-header/lineup-header.component';
import { ScatterChartComponent } from '../../shared/scatter-chart/scatter-chart.component';
import { SplitBarsComponent, SplitRow } from '../../shared/split-bars/split-bars.component';

const BAR_FLOOR_IN = 70;
const MAX_HEIGHT_IN = 90;

interface Tile {
  label: string;
  value: string;
  detail: string;
}

@Component({
  selector: 'rebounding-tab',
  imports: [LineupHeaderComponent, ScatterChartComponent, SplitBarsComponent],
  templateUrl: './rebounding.component.html',
  styleUrl: './rebounding.component.scss',
})
export class ReboundingComponent {
  readonly store = inject(LineupsStore);
  readonly lineupKey = lineupKey;
  readonly initials = initials;
  readonly pct = pct;
  readonly feetInches = feetInches;
  readonly sizeQuadrants: [string, string, string, string] = [
    'Small, still boards',
    'Big and owns the glass',
    'Small and outrebounded',
    'Big, but loses the glass',
  ];

  /** The selected lineup's size against the possession-weighted average of the lineups shown. */
  readonly size = computed(() => {
    const l = this.store.selected();
    const rows = this.store.visible().filter((row) => row.avg_height_in > 0);
    if (!l) {
      return null;
    }
    const weight = rows.reduce((sum, row) => sum + row.total_possessions, 0);
    const average = weight
      ? rows.reduce((sum, row) => sum + row.avg_height_in * row.total_possessions, 0) / weight
      : l.avg_height_in;
    const players = [...l.players].sort((a, b) => (b.height_in ?? 0) - (a.height_in ?? 0));
    return {
      height: feetInches(l.avg_height_in),
      weight: l.avg_weight_lb.toFixed(0),
      gap: l.avg_height_in - average,
      positions: [
        { label: 'Guards', count: l.guards },
        { label: 'Forwards', count: l.forwards },
        { label: 'Centers', count: l.centers },
      ],
      players: players.map((player) => ({
        ...player,
        height: feetInches(player.height_in),
        // Bars start at 5'10" so the differences between NBA players are visible.
        share: player.height_in ? Math.max(4, ((player.height_in - BAR_FLOOR_IN) / (MAX_HEIGHT_IN - BAR_FLOOR_IN)) * 100) : 0,
      })),
    };
  });
  readonly quadrants: [string, string, string, string] = [
    'Cleans the defensive glass',
    'Dominates the glass',
    'Gives up boards',
    'Crashes, then leaks back',
  ];

  readonly tiles = computed<Tile[]>(() => {
    const l = this.store.selected();
    const league = this.store.league();
    if (!l) {
      return [];
    }
    const gap = (value: number, average: number | undefined) =>
      average === undefined ? '' : `${signed((value - average) * 100)} pts vs league`;
    return [
      { label: 'Offensive rebound %', value: pct(l.oreb_pct), detail: gap(l.oreb_pct, league?.oreb) },
      { label: 'Defensive rebound %', value: pct(l.dreb_pct), detail: gap(l.dreb_pct, league?.dreb) },
      { label: 'Total rebound %', value: pct(l.total_reb_pct), detail: 'Of every rebound chance, both ends' },
      { label: 'Opponent offensive rebound %', value: pct(l.opponent_oreb_pct), detail: 'Lower is better for the lineup' },
    ];
  });

  readonly rows = computed<SplitRow[]>(() => {
    const l = this.store.selected();
    if (!l) {
      return [];
    }
    const opponentDreb = num(l, 'offensive_rebound_opportunities')
      ? num(l, 'offensive_rebounds_defense') / num(l, 'offensive_rebound_opportunities')
      : 0;
    return [
      { label: 'Offensive rebound %', left: l.oreb_pct, right: l.opponent_oreb_pct, format: 'pct' },
      { label: 'Defensive rebound %', left: l.dreb_pct, right: opponentDreb, format: 'pct' },
      { label: 'Total rebound %', left: l.total_reb_pct, right: 1 - l.total_reb_pct, format: 'pct' },
    ];
  });

  /** Best rebounding lineups among those with at least a handful of chances, so a single board doesn't top the list. */
  readonly leaders = computed(() =>
    [...this.store.visible()]
      .filter((row) => num(row, 'offensive_rebound_opportunities') + num(row, 'defensive_rebound_opportunities') >= 5)
      .sort((a, b) => b.total_reb_pct - a.total_reb_pct)
      .slice(0, 5),
  );

  signedInches(value: number): string {
    return `${signed(value)} in`;
  }

  names(lineup: LineupSummary): string {
    return lineup.players.map((player) => player.name).join(', ');
  }
}
