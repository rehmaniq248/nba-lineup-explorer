import { Component, computed, inject } from '@angular/core';
import { toObservable, toSignal } from '@angular/core/rxjs-interop';
import { combineLatest, of } from 'rxjs';
import { catchError, map, switchMap } from 'rxjs/operators';

import { ShotChart, ShotSplit } from '../../../_services/lineup.models';
import { num, pct, scaleColor, signed } from '../../../_services/lineup.utils';
import { LineupsService } from '../../../_services/lineups.service';
import { LineupsStore } from '../../../_services/lineups.store';
import { LineupHeaderComponent } from '../../shared/lineup-header/lineup-header.component';
import { ShotChartComponent } from '../../shared/shot-chart/shot-chart.component';

interface ZoneRow {
  label: string;
  lineup: string;
  lineupPct: string;
  lineupVs: string;
  lineupColor: string;
  opponent: string;
  opponentPct: string;
  opponentVs: string;
  opponentColor: string;
  league: string;
}

interface TypeRow {
  label: string;
  lineupShare: number;
  opponentShare: number;
  leagueShare: number;
  lineupPct: string;
  opponentPct: string;
  leaguePct: string;
}

// Ten points of FG% above or below league average saturates the table's colour chips.
const ZONE_SATURATION = 0.1;

interface Charts {
  offense: ShotChart;
  defense: ShotChart;
}

@Component({
  selector: 'shooting-tab',
  imports: [LineupHeaderComponent, ShotChartComponent],
  templateUrl: './shooting.component.html',
  styleUrl: './shooting.component.scss',
})
export class ShootingComponent {
  readonly store = inject(LineupsStore);
  private readonly api = inject(LineupsService);
  readonly pct = pct;

  private readonly request = computed(() => {
    const lineup = this.store.selected();
    return lineup ? { context: this.store.context(), teamId: lineup.team_id, playerIds: lineup.player_ids } : null;
  });

  /** Shots taken by the selected lineup and by opponents against it, under the shared filters. */
  readonly charts = toSignal(
    toObservable(this.request).pipe(
      switchMap((request) => {
        if (!request) {
          return of(null);
        }
        const query = { ...request.context, team_id: request.teamId, player_ids: request.playerIds };
        return combineLatest([
          this.api.getShots({ ...query, side: 'offense' }),
          this.api.getShots({ ...query, side: 'defense' }),
        ]).pipe(
          map(([offense, defense]): Charts => ({ offense, defense })),
          catchError(() => of(null)),
        );
      }),
    ),
    { initialValue: null },
  );

  readonly zones = computed<ZoneRow[]>(() => {
    const charts = this.charts();
    if (!charts) {
      return [];
    }
    const rows = charts.offense.zones.map((zone, index) => {
      const opponent = charts.defense.zones[index];
      return {
        label: zone.label,
        ...this.cells('lineup', zone, 1),
        ...this.cells('opponent', opponent, -1),
        league: pct(zone.league_pct),
      } as ZoneRow;
    });
    // Free throws aren't on the chart, so they come from the lineup's possession sums.
    const lineup = this.store.selected();
    const league = this.store.league();
    if (lineup) {
      const made = num(lineup, 'offensive_ft_made');
      const attempted = num(lineup, 'offensive_ft_attempted');
      const oppMade = num(lineup, 'defensive_ft_made');
      const oppAttempted = num(lineup, 'defensive_ft_attempted');
      const vs = (value: number) => (league ? value - league.ft : 0);
      rows.push({
        label: 'Free throws',
        lineup: `${made}/${attempted}`,
        lineupPct: attempted ? pct(made / attempted) : '—',
        lineupVs: attempted && league ? signed(vs(made / attempted) * 100) : '',
        lineupColor: attempted ? scaleColor(vs(made / attempted) / ZONE_SATURATION) : 'transparent',
        opponent: `${oppMade}/${oppAttempted}`,
        opponentPct: oppAttempted ? pct(oppMade / oppAttempted) : '—',
        opponentVs: oppAttempted && league ? signed(vs(oppMade / oppAttempted) * 100) : '',
        opponentColor: oppAttempted ? scaleColor(-vs(oppMade / oppAttempted) / ZONE_SATURATION) : 'transparent',
        league: league ? pct(league.ft) : '—',
      });
    }
    return rows;
  });

  readonly types = computed<TypeRow[]>(() => {
    const charts = this.charts();
    if (!charts) {
      return [];
    }
    return charts.offense.shot_types.map((type, index) => {
      const opponent = charts.defense.shot_types[index];
      return {
        label: type.label,
        lineupShare: type.share * 100,
        opponentShare: opponent.share * 100,
        leagueShare: type.league_share * 100,
        lineupPct: type.attempted ? pct(type.pct, 0) : '—',
        opponentPct: opponent.attempted ? pct(opponent.pct, 0) : '—',
        leaguePct: pct(type.league_pct, 0),
      };
    });
  });

  /** For opponents the colour is flipped: holding them below league average is the good outcome. */
  private cells(prefix: 'lineup' | 'opponent', split: ShotSplit, direction: 1 | -1): Partial<ZoneRow> {
    const has = split.attempted > 0;
    return {
      [prefix]: `${split.made}/${split.attempted}`,
      [`${prefix}Pct`]: has ? pct(split.pct) : '—',
      [`${prefix}Vs`]: has ? signed(split.vs_league * 100) : '',
      [`${prefix}Color`]: has ? scaleColor((direction * split.vs_league) / ZONE_SATURATION) : 'transparent',
    };
  }
}
