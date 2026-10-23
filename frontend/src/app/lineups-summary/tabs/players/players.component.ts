import { Component, computed, inject, signal } from '@angular/core';
import { toObservable, toSignal } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { of, timer } from 'rxjs';
import { catchError, debounce, map, switchMap, tap } from 'rxjs/operators';

import { LineupSummary, PlayerOnOff } from '../../../_services/lineup.models';
import { feetInches, initials, pct, scaleColor, signed } from '../../../_services/lineup.utils';
import { LineupsService } from '../../../_services/lineups.service';
import { LineupsStore } from '../../../_services/lineups.store';
import { SplitBarsComponent, SplitRow } from '../../shared/split-bars/split-bars.component';

type Order = 'asc' | 'desc';

interface Column {
  label: string;
  sortKey: string;
  firstOrder: Order;
  hint: string;
}

const PAGE_SIZE = 100;
const SEARCH_DEBOUNCE_MS = 250;
// An on/off gap of ±15 per 100 possessions saturates the colour.
const ON_OFF_SATURATION = 15;
const TEAMMATE_MIN_POSSESSIONS = 200;

/**
 * Player impact: how a player's team plays with him on the floor against the same team with him on the bench.
 * Uses the shared context filters (team, games, venue, clutch) so it lines up with the lineup tabs.
 */
@Component({
  selector: 'players-tab',
  imports: [FormsModule, SplitBarsComponent],
  templateUrl: './players.component.html',
  styleUrl: './players.component.scss',
})
export class PlayersComponent {
  readonly store = inject(LineupsStore);
  private readonly api = inject(LineupsService);
  private readonly router = inject(Router);

  readonly search = signal('');
  readonly minPossessions = signal(1500);
  readonly sortBy = signal('on_off_net');
  readonly order = signal<Order>('desc');
  private readonly selectedId = signal<string | null>(null);

  readonly loading = signal(true);
  readonly error = signal('');

  readonly signed = signed;
  readonly pct = pct;
  readonly initials = initials;
  readonly feetInches = feetInches;
  readonly color = (value: number) => scaleColor(value / ON_OFF_SATURATION);

  readonly columns: Column[] = [
    { label: 'Poss', sortKey: 'possessions', firstOrder: 'desc', hint: 'Possessions on the floor, offense plus defense' },
    { label: 'PPG', sortKey: 'points_per_game', firstOrder: 'desc', hint: 'Regular season points per game (box score)' },
    { label: 'On', sortKey: 'on_net_rating', firstOrder: 'desc', hint: "Team net rating with him on the floor" },
    { label: 'Off', sortKey: 'off_net_rating', firstOrder: 'asc', hint: 'Team net rating with him on the bench' },
    { label: 'On/off', sortKey: 'on_off_net', firstOrder: 'desc', hint: 'On minus off: how much better the team is with him' },
  ];

  private readonly request = computed(() => ({
    context: this.store.context(),
    search: this.search().trim(),
    min_possessions: this.minPossessions(),
    sort_by: this.sortBy(),
    order: this.order(),
  }));

  private readonly page = toSignal(
    toObservable(this.request).pipe(
      debounce((request) => (request.search ? timer(SEARCH_DEBOUNCE_MS) : of(null))),
      tap(() => {
        this.loading.set(true);
        this.error.set('');
      }),
      switchMap((request) =>
        this.api
          .getPlayers({
            ...request.context,
            search: request.search,
            min_possessions: request.min_possessions,
            sort_by: request.sort_by,
            order: request.order,
            limit: PAGE_SIZE,
          })
          .pipe(
            catchError((err) => {
              this.error.set(err?.message ?? 'Players could not be loaded.');
              return of({ players: [] as PlayerOnOff[], total: 0 });
            }),
          ),
      ),
      tap(() => this.loading.set(false)),
    ),
    { initialValue: { players: [] as PlayerOnOff[], total: 0 } },
  );

  readonly players = computed(() => this.page().players);
  readonly total = computed(() => this.page().total);

  readonly selected = computed(() => {
    const rows = this.players();
    return rows.find((row) => this.rowKey(row) === this.selectedId()) ?? rows[0] ?? null;
  });

  private readonly maxAbs = computed(() => Math.max(5, ...this.players().map((row) => Math.abs(row.on_off_net))));

  readonly splitRows = computed<SplitRow[]>(() => {
    const p = this.selected();
    if (!p) {
      return [];
    }
    return [
      { label: 'Offensive rating', left: p.on.offensive_rating / 100, right: p.off.offensive_rating / 100, format: 'per100' },
      { label: 'Defensive rating', left: p.on.defensive_rating / 100, right: p.off.defensive_rating / 100, format: 'per100', lowerWins: true },
      { label: 'Effective FG%', left: p.on.offensive_efg_pct, right: p.off.offensive_efg_pct, format: 'pct' },
      { label: 'Opponent eFG%', left: p.on.defensive_efg_pct, right: p.off.defensive_efg_pct, format: 'pct', lowerWins: true },
      { label: 'Turnover rate', left: p.on.offensive_turnover_rate, right: p.off.offensive_turnover_rate, format: 'pct', lowerWins: true },
      { label: 'Offensive rebound %', left: p.on.oreb_pct, right: p.off.oreb_pct, format: 'pct' },
      { label: 'Defensive rebound %', left: p.on.dreb_pct, right: p.off.dreb_pct, format: 'pct' },
    ];
  });

  /** The selected player's best two-man pairings on his team. */
  readonly teammates = toSignal(
    toObservable(computed(() => ({ player: this.selected(), context: this.store.context() }))).pipe(
      switchMap(({ player, context }) => {
        if (!player) {
          return of([] as LineupSummary[]);
        }
        return this.api
          .getLineups({
            ...context,
            team_id: player.team_id,
            lineup_size: 2,
            player_ids: [player.player_id],
            min_possessions: TEAMMATE_MIN_POSSESSIONS,
            sort_by: 'net_rating',
            order: 'desc',
            limit: 8,
          })
          .pipe(
            map((page) => page.lineups),
            catchError(() => of([] as LineupSummary[])),
          );
      }),
    ),
    { initialValue: [] as LineupSummary[] },
  );

  readonly teammateMax = computed(() => Math.max(5, ...this.teammates().map((row) => Math.abs(row.net_rating))));

  rowKey(row: PlayerOnOff): string {
    return `${row.player_id}|${row.team_id}`;
  }

  select(row: PlayerOnOff): void {
    this.selectedId.set(this.rowKey(row));
  }

  sortOn(column: Column): void {
    if (this.sortBy() === column.sortKey) {
      this.order.set(this.order() === 'desc' ? 'asc' : 'desc');
    } else {
      this.sortBy.set(column.sortKey);
      this.order.set(column.firstOrder);
    }
  }

  ariaSort(column: Column): 'ascending' | 'descending' | 'none' {
    if (this.sortBy() !== column.sortKey) {
      return 'none';
    }
    return this.order() === 'asc' ? 'ascending' : 'descending';
  }

  cell(row: PlayerOnOff, column: Column): string {
    switch (column.sortKey) {
      case 'possessions':
        return row.possessions.toLocaleString();
      case 'points_per_game':
        return row.points_per_game.toFixed(1);
      case 'on_net_rating':
        return signed(row.on.net_rating);
      case 'off_net_rating':
        return row.off_possessions ? signed(row.off.net_rating) : '—';
      default:
        return signed(row.on_off_net);
    }
  }

  barWidth(value: number): number {
    return (Math.abs(value) / this.maxAbs()) * 50;
  }

  teammateName(row: LineupSummary, playerId: string): string {
    return row.players.find((player) => player.player_id !== playerId)?.name ?? '';
  }

  teammateWidth(value: number): number {
    return (Math.abs(value) / this.teammateMax()) * 100;
  }

  draft(player: PlayerOnOff): string {
    if (!player.draft_year) {
      return '—';
    }
    if (!player.draft_number) {
      return `${player.draft_year} · Undrafted`;
    }
    return `${player.draft_year} · R${player.draft_round ?? 1} #${player.draft_number}`;
  }

  age(player: PlayerOnOff): string {
    if (!player.birth_date) {
      return '—';
    }
    const born = new Date(`${player.birth_date.slice(0, 10)}T12:00:00`);
    // Age at the end of the 2025-26 regular season.
    const seasonEnd = new Date('2026-04-12T12:00:00');
    let years = seasonEnd.getFullYear() - born.getFullYear();
    if (seasonEnd < new Date(seasonEnd.getFullYear(), born.getMonth(), born.getDate())) {
      years -= 1;
    }
    return String(years);
  }

  /** Jump to the lineup tabs, narrowed to five-man units that include this player. */
  openLineups(player: PlayerOnOff): void {
    this.store.focusPlayer({ player_id: player.player_id, name: player.name }, player.team_id);
    this.store.setMinPossessions(0);
    this.store.setSize(5);
    this.router.navigate(['/lineups-summary'], { queryParamsHandling: 'preserve' });
  }
}
