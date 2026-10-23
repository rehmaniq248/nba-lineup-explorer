import { Component, computed, inject } from '@angular/core';
import { RouterLink } from '@angular/router';

import { LineupSummary } from '../../../_services/lineup.models';
import { initials, lineupKey, pct, scaleColor, signed } from '../../../_services/lineup.utils';
import { LineupsStore, PAGE_SIZE } from '../../../_services/lineups.store';
import { LineupHeaderComponent } from '../../shared/lineup-header/lineup-header.component';

interface Column {
  label: string;
  sortKey: string;
  /** The direction a first click sorts in: the "best first" direction for the metric. */
  firstOrder: 'asc' | 'desc';
  hint: string;
}

interface Kpi {
  label: string;
  value: string;
  detail: string;
}

const NET_BAR_SATURATION = 30;

@Component({
  selector: 'overview-tab',
  imports: [RouterLink, LineupHeaderComponent],
  templateUrl: './overview.component.html',
  styleUrl: './overview.component.scss',
})
export class OverviewComponent {
  readonly store = inject(LineupsStore);

  readonly columns: Column[] = [
    { label: 'Poss', sortKey: 'total_possessions', firstOrder: 'desc', hint: 'Possessions on the floor, offense plus defense' },
    { label: 'Min', sortKey: 'minutes', firstOrder: 'desc', hint: 'Minutes played together' },
    { label: 'ORtg', sortKey: 'offensive_rating', firstOrder: 'desc', hint: 'Points scored per 100 possessions' },
    { label: 'DRtg', sortKey: 'defensive_rating', firstOrder: 'asc', hint: 'Points allowed per 100 possessions. Lower is better' },
    { label: 'Net', sortKey: 'net_rating', firstOrder: 'desc', hint: 'ORtg minus DRtg' },
    { label: 'eFG%', sortKey: 'offensive_efg_pct', firstOrder: 'desc', hint: 'Effective field goal %, counting threes at 1.5' },
    { label: 'TOV%', sortKey: 'offensive_turnover_rate', firstOrder: 'asc', hint: 'Turnovers per offensive possession. Lower is better' },
    { label: 'OREB%', sortKey: 'oreb_pct', firstOrder: 'desc', hint: 'Share of offensive rebound chances won' },
  ];

  readonly tabs = [
    { path: '../matchup', label: 'Matchup', detail: 'Lineup against its opponents, plus how the points were created' },
    { path: '../shooting', label: 'Shooting', detail: 'Shot chart, six NBA zones and shot types vs league' },
    { path: '../rebounding', label: 'Rebounding', detail: 'Offensive and defensive glass, and lineup size' },
    { path: '../ball-security', label: 'Ball security', detail: 'Turnovers, steals and blocks' },
  ];

  readonly pageSize = PAGE_SIZE;
  readonly meterSteps = Array.from({ length: 10 }, (_, index) => index);
  readonly initials = initials;
  readonly lineupKey = lineupKey;
  readonly signed = signed;
  readonly pct = pct;

  readonly maxAbsNet = computed(() => Math.max(1, ...this.store.visible().map((row) => Math.abs(row.net_rating))));

  readonly kpis = computed<Kpi[]>(() => {
    const rows = this.store.visible();
    if (!rows.length) {
      return [];
    }
    const names = (row: LineupSummary) => row.players.map((player) => player.name.split(' ')[0]).join(' · ');
    const best = (pick: (row: LineupSummary) => number, direction: 1 | -1) =>
      rows.reduce((top, row) => (pick(row) * direction > pick(top) * direction ? row : top));
    const bestNet = best((row) => row.net_rating, 1);
    const bestOff = best((row) => row.offensive_rating, 1);
    const bestDef = best((row) => row.defensive_rating, -1);
    return [
      { label: 'Best net rating', value: signed(bestNet.net_rating), detail: names(bestNet) },
      { label: 'Best offense', value: bestOff.offensive_rating.toFixed(1), detail: names(bestOff) },
      { label: 'Best defense', value: bestDef.defensive_rating.toFixed(1), detail: names(bestDef) },
    ];
  });

  readonly positiveShare = computed(() => {
    const rows = this.store.visible();
    return rows.length ? rows.filter((row) => row.net_rating > 0).length / rows.length : 0;
  });
  readonly meterLit = computed(() => Math.round(this.positiveShare() * 10));

  ariaSort(column: Column): 'ascending' | 'descending' | 'none' {
    if (this.store.sortBy() !== column.sortKey) {
      return 'none';
    }
    return this.store.order() === 'asc' ? 'ascending' : 'descending';
  }

  cell(lineup: LineupSummary, column: Column): string {
    const value = Number(lineup[column.sortKey] ?? 0);
    switch (column.label) {
      case 'Poss':
        return String(lineup.total_possessions);
      case 'Min':
        return lineup.minutes.toFixed(1);
      case 'ORtg':
      case 'DRtg':
        return value.toFixed(1);
      default:
        return pct(value);
    }
  }

  netColor(net: number): string {
    return scaleColor(net / NET_BAR_SATURATION);
  }

  netBarWidth(net: number): number {
    return (Math.abs(net) / this.maxAbsNet()) * 50;
  }
}
