import { Injectable, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { Subject, of, timer } from 'rxjs';
import { catchError, debounce, switchMap, tap } from 'rxjs/operators';

import {
  ContextFilters,
  DatasetMeta,
  GameType,
  LeagueAverages,
  LineupFilters,
  LineupSummary,
  Location,
  Team,
} from './lineup.models';
import { lineupKey } from './lineup.utils';
import { LineupsService } from './lineups.service';

export const PAGE_SIZE = 100;

type Order = 'asc' | 'desc';

const DEFAULTS = { size: 5, min: 250, sort: 'net_rating', order: 'desc' as Order };
const SEARCH_DEBOUNCE_MS = 250;

export const GAME_TYPES: { value: GameType | ''; label: string }[] = [
  { value: '', label: 'Full season' },
  { value: 'Regular Season', label: 'Regular season' },
  { value: 'Playoffs', label: 'Playoffs' },
  { value: 'Play-In', label: 'Play-in' },
];

export const LOCATIONS: { value: Location | ''; label: string }[] = [
  { value: '', label: 'All' },
  { value: 'home', label: 'Home' },
  { value: 'away', label: 'Away' },
];

/** A player the lineup list is narrowed to (set from the Players tab). */
export interface PlayerFocus {
  player_id: string;
  name: string;
}

/**
 * Filters, results and the selected lineup, shared by every dashboard tab. Filter state lives in the URL so a
 * view can be shared by link and survives a refresh.
 */
@Injectable({ providedIn: 'root' })
export class LineupsStore {
  private readonly api = inject(LineupsService);
  private readonly router = inject(Router);
  private readonly fetch$ = new Subject<{ debounced: boolean }>();
  private readonly league$ = new Subject<void>();

  readonly lineupSize = signal(DEFAULTS.size);
  readonly teamId = signal('');
  readonly gameType = signal<GameType | ''>('');
  readonly location = signal<Location | ''>('');
  readonly clutch = signal(false);
  readonly minPossessions = signal(DEFAULTS.min);
  readonly sortBy = signal(DEFAULTS.sort);
  readonly order = signal<Order>(DEFAULTS.order);
  readonly search = signal('');
  readonly player = signal<PlayerFocus | null>(null);
  private readonly selectedKey = signal<string | null>(null);

  readonly teams = signal<Team[]>([]);
  readonly meta = signal<DatasetMeta | null>(null);
  readonly league = signal<LeagueAverages | null>(null);
  readonly lineups = signal<LineupSummary[]>([]);
  readonly total = signal(0);
  readonly loading = signal(true);
  readonly error = signal('');

  /** Lineups shown on every tab. Player search runs on the server, so this is the loaded page as is. */
  readonly visible = computed(() => this.lineups());

  readonly team = computed(() => this.teams().find((team) => team.team_id === this.teamId()) ?? null);

  /** The season slice every request shares: lineups, players, shots and league averages. */
  readonly context = computed<ContextFilters>(() => ({
    team_id: this.teamId(),
    game_type: this.gameType(),
    location: this.location(),
    clutch: this.clutch(),
  }));

  readonly selected = computed(() => {
    const rows = this.visible();
    return rows.find((row) => lineupKey(row) === this.selectedKey()) ?? rows[0] ?? null;
  });
  readonly selectedId = computed(() => {
    const row = this.selected();
    return row ? lineupKey(row) : null;
  });

  constructor() {
    this.readUrl();

    this.fetch$
      .pipe(
        debounce(({ debounced }) => (debounced ? timer(SEARCH_DEBOUNCE_MS) : of(null))),
        tap(() => {
          this.loading.set(true);
          this.error.set('');
        }),
        switchMap(() =>
          this.api.getLineups(this.filters()).pipe(
            catchError((err) => {
              this.error.set(err?.error?.detail ?? err?.message ?? 'The lineup data could not be loaded.');
              return of(null);
            }),
          ),
        ),
      )
      .subscribe((page) => {
        this.lineups.set(page?.lineups ?? []);
        this.total.set(page?.total ?? 0);
        this.loading.set(false);
      });

    this.league$
      .pipe(switchMap(() => this.api.getLeague(this.context()).pipe(catchError(() => of(null)))))
      .subscribe((league) => this.league.set(league));

    this.api.getTeams().subscribe({ next: (teams) => this.teams.set(teams), error: () => undefined });
    this.api.getMeta().subscribe({ next: (meta) => this.meta.set(meta), error: () => undefined });
    this.fetch$.next({ debounced: false });
    this.league$.next();
  }

  setSize(size: number): void {
    this.lineupSize.set(size);
    this.refresh();
  }

  setTeam(teamId: string): void {
    this.teamId.set(teamId);
    this.refresh();
  }

  setGameType(gameType: GameType | ''): void {
    this.gameType.set(gameType);
    this.refresh(true);
  }

  setLocation(location: Location | ''): void {
    this.location.set(location);
    this.refresh();
  }

  setClutch(clutch: boolean): void {
    this.clutch.set(clutch);
    this.refresh(true);
  }

  setMinPossessions(value: number): void {
    this.minPossessions.set(value);
    this.refresh();
  }

  setSearch(value: string): void {
    this.search.set(value);
    this.writeUrl();
    this.fetch$.next({ debounced: true });
  }

  /** Narrow the lineups to those including one player, e.g. from the Players tab. */
  focusPlayer(player: PlayerFocus | null, teamId?: string): void {
    this.player.set(player);
    if (teamId !== undefined) {
      this.teamId.set(teamId);
    }
    this.refresh();
  }

  /** Sorts the leaderboard; `firstOrder` is the "best first" direction used the first time a column is chosen. */
  sortOn(sortKey: string, firstOrder: Order): void {
    if (this.sortBy() === sortKey) {
      this.order.set(this.order() === 'desc' ? 'asc' : 'desc');
    } else {
      this.sortBy.set(sortKey);
      this.order.set(firstOrder);
    }
    this.refresh();
  }

  select(lineup: LineupSummary): void {
    this.selectedKey.set(lineupKey(lineup));
    this.writeUrl();
  }

  clearFilters(): void {
    this.teamId.set('');
    this.gameType.set('');
    this.location.set('');
    this.clutch.set(false);
    this.search.set('');
    this.player.set(null);
    this.minPossessions.set(0);
    this.refresh(true);
  }

  /** The current lineup query, for tabs that need a differently sorted slice of the same lineups. */
  filters(): LineupFilters {
    return {
      ...this.context(),
      lineup_size: this.lineupSize(),
      min_possessions: this.minPossessions(),
      player_ids: this.player() ? [this.player()!.player_id] : [],
      search: this.search().trim(),
      sort_by: this.sortBy(),
      order: this.order(),
      limit: PAGE_SIZE,
    };
  }

  /** `leagueChanged`: the filter changes which games count, so league averages are refetched too. */
  private refresh(leagueChanged = false): void {
    this.writeUrl();
    this.fetch$.next({ debounced: false });
    if (leagueChanged) {
      this.league$.next();
    }
  }

  private readUrl(): void {
    const params = new URLSearchParams(window.location.search);
    const size = Number(params.get('size'));
    if (size >= 1 && size <= 5) {
      this.lineupSize.set(Math.floor(size));
    }
    this.teamId.set(params.get('team') ?? '');
    const gameType = params.get('games');
    this.gameType.set(GAME_TYPES.some((option) => option.value === gameType) ? (gameType as GameType) : '');
    const location = params.get('at');
    this.location.set(location === 'home' || location === 'away' ? location : '');
    this.clutch.set(params.get('clutch') === '1');
    const min = params.get('min');
    if (min !== null && Number(min) >= 0) {
      this.minPossessions.set(Number(min));
    }
    this.sortBy.set(params.get('sort') || DEFAULTS.sort);
    this.order.set(params.get('order') === 'asc' ? 'asc' : 'desc');
    this.search.set(params.get('q') ?? '');
    const playerId = params.get('player');
    this.player.set(playerId ? { player_id: playerId, name: params.get('playerName') ?? 'Player' } : null);
    const lineup = params.get('lineup');
    this.selectedKey.set(lineup ? lineup.split(',').join('|') : null);
  }

  private writeUrl(): void {
    const nonDefault = <T>(value: T, fallback: T): T | null => (value === fallback ? null : value);
    this.router.navigate([], {
      queryParams: {
        size: nonDefault(this.lineupSize(), DEFAULTS.size),
        team: this.teamId() || null,
        games: this.gameType() || null,
        at: this.location() || null,
        clutch: this.clutch() ? 1 : null,
        min: nonDefault(this.minPossessions(), DEFAULTS.min),
        sort: nonDefault(this.sortBy(), DEFAULTS.sort),
        order: nonDefault(this.order(), DEFAULTS.order),
        q: this.search() || null,
        player: this.player()?.player_id ?? null,
        playerName: this.player()?.name ?? null,
        lineup: this.selectedId()?.split('|').join(',') ?? null,
      },
      queryParamsHandling: 'merge',
      replaceUrl: true,
    });
  }
}
