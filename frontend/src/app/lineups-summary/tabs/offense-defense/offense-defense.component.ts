import { Component, computed, inject } from '@angular/core';
import { toObservable, toSignal } from '@angular/core/rxjs-interop';
import { of } from 'rxjs';
import { catchError, map, switchMap } from 'rxjs/operators';

import { LineupSummary } from '../../../_services/lineup.models';
import { initials, lineupKey, scaleColor, signed } from '../../../_services/lineup.utils';
import { LineupsService } from '../../../_services/lineups.service';
import { LineupsStore } from '../../../_services/lineups.store';
import { ScatterChartComponent } from '../../shared/scatter-chart/scatter-chart.component';

const NET_SATURATION = 30;

@Component({
  selector: 'offense-defense-tab',
  imports: [ScatterChartComponent],
  templateUrl: './offense-defense.component.html',
  styleUrl: './offense-defense.component.scss',
})
export class OffenseDefenseComponent {
  readonly store = inject(LineupsStore);
  private readonly api = inject(LineupsService);
  readonly lineupKey = lineupKey;
  readonly initials = initials;
  readonly signed = signed;
  readonly quadrants: [string, string, string, string] = [
    "Stops, doesn't score",
    'Scores and stops',
    'Neither',
    "Scores, doesn't stop",
  ];

  private readonly ranked = computed(() => [...this.store.visible()].sort((a, b) => b.net_rating - a.net_rating));
  readonly best = computed(() => this.ranked().slice(0, 5));
  /** The loaded page holds the best lineups, so the bottom five are fetched with the same filters, worst first. */
  readonly worst = toSignal(
    toObservable(computed(() => ({ ...this.store.filters(), sort_by: 'net_rating', order: 'asc' as const, limit: 5 }))).pipe(
      switchMap((filters) =>
        this.api.getLineups(filters).pipe(
          map((page) => page.lineups),
          catchError(() => of(this.ranked().slice(-5).reverse())),
        ),
      ),
    ),
    { initialValue: [] as LineupSummary[] },
  );
  private readonly maxAbs = computed(() =>
    Math.max(1, ...[...this.store.visible(), ...this.worst()].map((row) => Math.abs(row.net_rating))),
  );

  names(lineup: LineupSummary): string {
    return lineup.players.map((player) => player.name).join(', ');
  }

  width(net: number): number {
    return (Math.abs(net) / this.maxAbs()) * 100;
  }

  color(net: number): string {
    return scaleColor(net / NET_SATURATION);
  }
}
