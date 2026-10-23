import { Component, computed, inject } from '@angular/core';

import { LineupSummary } from '../../../_services/lineup.models';
import { num, pct } from '../../../_services/lineup.utils';
import { LineupsStore } from '../../../_services/lineups.store';
import { LineupHeaderComponent } from '../../shared/lineup-header/lineup-header.component';
import { ScatterChartComponent } from '../../shared/scatter-chart/scatter-chart.component';
import { SplitBarsComponent, SplitRow } from '../../shared/split-bars/split-bars.component';

interface Tile {
  label: string;
  value: string;
  detail: string;
}

const perPossession = (lineup: LineupSummary, stat: string, possessions: string): number =>
  num(lineup, possessions) ? num(lineup, stat) / num(lineup, possessions) : 0;

@Component({
  selector: 'ball-security-tab',
  imports: [LineupHeaderComponent, ScatterChartComponent, SplitBarsComponent],
  templateUrl: './ball-security.component.html',
  styleUrl: './ball-security.component.scss',
})
export class BallSecurityComponent {
  readonly store = inject(LineupsStore);
  readonly quadrants: [string, string, string, string] = [
    'Protects and forces',
    'Forces, but careless',
    'Safe, but passive',
    'Careless and passive',
  ];

  // Steals and blocks happen on the defending side of a possession, so a lineup's own come from its defensive rows.
  readonly tiles = computed<Tile[]>(() => {
    const l = this.store.selected();
    const league = this.store.league();
    if (!l) {
      return [];
    }
    return [
      {
        label: 'Turnover rate',
        value: pct(l.offensive_turnover_rate),
        detail: league ? `League ${pct(league.turnover)}. Lower is better` : 'Lower is better',
      },
      { label: 'Turnovers forced', value: pct(l.defensive_turnover_rate), detail: 'Of opponent possessions' },
      { label: 'Steals', value: String(num(l, 'defensive_steals')), detail: 'On defense' },
      { label: 'Blocks', value: String(num(l, 'defensive_blocks')), detail: 'On defense' },
    ];
  });

  readonly rows = computed<SplitRow[]>(() => {
    const l = this.store.selected();
    if (!l) {
      return [];
    }
    return [
      { label: 'Turnover rate', left: l.offensive_turnover_rate, right: l.defensive_turnover_rate, format: 'pct', lowerWins: true },
      {
        label: 'Steals per 100 possessions',
        left: perPossession(l, 'defensive_steals', 'defensive_possessions'),
        right: perPossession(l, 'offensive_steals', 'offensive_possessions'),
        format: 'per100',
      },
      {
        label: 'Blocks per 100 possessions',
        left: perPossession(l, 'defensive_blocks', 'defensive_possessions'),
        right: perPossession(l, 'offensive_blocks', 'offensive_possessions'),
        format: 'per100',
      },
      {
        label: 'Assists per made shot',
        left: l.offensive_assist_rate,
        right: num(l, 'defensive_fg_made') ? num(l, 'defensive_assists') / num(l, 'defensive_fg_made') : 0,
        format: 'pct',
      },
    ];
  });
}
