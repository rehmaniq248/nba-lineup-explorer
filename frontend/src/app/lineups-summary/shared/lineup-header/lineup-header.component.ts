import { Component, computed, inject, input } from '@angular/core';
import { toObservable, toSignal } from '@angular/core/rxjs-interop';
import { of } from 'rxjs';
import { catchError, switchMap } from 'rxjs/operators';

import { LineupSummary, TrendPoint } from '../../../_services/lineup.models';
import { feetInches, monthLabel, scaleColor, signed } from '../../../_services/lineup.utils';
import { LineupsService } from '../../../_services/lineups.service';
import { LineupsStore } from '../../../_services/lineups.store';

// A month needs this many possessions before its bar is drawn at full strength.
const TREND_MIN_POSSESSIONS = 20;
const TREND_HEIGHT = 44;
const TREND_SATURATION = 30;

interface TrendBar {
  month: string;
  label: string;
  net: number;
  height: number;
  up: boolean;
  color: string;
  thin: boolean;
  title: string;
}

/** Roster, net rating, size and season trend of the selected lineup, at the top of every lineup-specific tab. */
@Component({
  selector: 'lineup-header',
  templateUrl: './lineup-header.component.html',
  styleUrl: './lineup-header.component.scss',
})
export class LineupHeaderComponent {
  private readonly api = inject(LineupsService);
  private readonly store = inject(LineupsStore);

  readonly lineup = input.required<LineupSummary>();

  readonly signed = signed;
  readonly feetInches = feetInches;
  readonly color = (net: number): string => scaleColor(net / 30);
  readonly half = TREND_HEIGHT / 2;

  private readonly request = computed(() => ({
    teamId: this.lineup().team_id,
    playerIds: this.lineup().player_ids,
    context: { ...this.store.context(), team_id: '' },
  }));

  private readonly trend = toSignal(
    toObservable(this.request).pipe(
      switchMap(({ teamId, playerIds, context }) =>
        this.api.getTrend(teamId, playerIds, context).pipe(catchError(() => of([] as TrendPoint[]))),
      ),
    ),
    { initialValue: [] as TrendPoint[] },
  );

  readonly bars = computed<TrendBar[]>(() => {
    const points = this.trend();
    const maxAbs = Math.max(10, ...points.map((point) => Math.abs(point.net_rating)));
    return points.map((point) => {
      const possessions = point.offensive_possessions + point.defensive_possessions;
      return {
        month: point.month,
        label: monthLabel(point.month),
        net: point.net_rating,
        height: Math.max(1, (Math.abs(point.net_rating) / maxAbs) * this.half),
        up: point.net_rating >= 0,
        color: scaleColor(point.net_rating / TREND_SATURATION),
        thin: possessions < TREND_MIN_POSSESSIONS,
        title: `${monthLabel(point.month)}: ${signed(point.net_rating)} net over ${possessions} possessions`,
      };
    });
  });

  readonly build = computed(() => {
    const lineup = this.lineup();
    const parts = [
      lineup.guards ? `${lineup.guards}G` : '',
      lineup.forwards ? `${lineup.forwards}F` : '',
      lineup.centers ? `${lineup.centers}C` : '',
    ].filter(Boolean);
    return parts.join(' · ');
  });
}
