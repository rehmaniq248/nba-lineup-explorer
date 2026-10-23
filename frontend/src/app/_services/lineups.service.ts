import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { map } from 'rxjs/operators';

import {
  ContextFilters,
  DatasetMeta,
  LeagueAverages,
  LineupFilters,
  LineupsPage,
  LineupSummary,
  PlayerFilters,
  PlayerOnOff,
  PlayersPage,
  ShotChart,
  Team,
  TrendPoint,
} from './lineup.models';

import { BaseService } from './base.service';

@Injectable({ providedIn: 'root' })
export class LineupsService extends BaseService {
  constructor(protected override http: HttpClient) {
    super(http);
  }

  private buildQueryParams(queryParams: Record<string, string | number>): HttpParams {
    return Object.entries(queryParams).reduce(
      (params, [key, value]) => params.set(key, String(value)),
      new HttpParams(),
    );
  }

  private buildDisplayedEndpointWithParams(
    endpoint: string,
    queryParams: Record<string, string | number>,
  ): string {
    const queryString = new URLSearchParams(
      Object.entries(queryParams).map(([key, value]) => [key, String(value)]),
    ).toString();
    return queryString ? `${endpoint}?${queryString}` : endpoint;
  }

  /** Array filters are sent comma-separated; empty values and `false` flags are omitted. */
  private filterParams(filters: object): HttpParams {
    let params = new HttpParams();
    for (const [key, value] of Object.entries(filters)) {
      const serialized = Array.isArray(value) ? value.join(',') : value;
      if (serialized !== undefined && serialized !== null && serialized !== '' && serialized !== false) {
        params = params.set(key, String(serialized));
      }
    }
    return params;
  }

  getLineupsLeagueSummary(lineupSize: number = 5, limit: number = 25): Observable<{
    endpoint: string;
    apiResponse: unknown;
  }> {
    const endpoint = `${this.baseUrl}/lineups`;
    const queryParams = { lineup_size: lineupSize, min_possessions: 100, limit };
    const params = this.buildQueryParams(queryParams);
    const displayedEndpointWithParams = this.buildDisplayedEndpointWithParams(endpoint, queryParams);

    return this.get(endpoint, params).pipe(
      map((data) => ({
        endpoint: displayedEndpointWithParams,
        apiResponse: data,
      })),
    );
  }

  /** Typed, filterable lineup query. */
  getLineups(filters: LineupFilters = {}): Observable<LineupsPage> {
    return this.http
      .get<LineupSummary[]>(`${this.baseUrl}/lineups`, {
        headers: this.headers,
        params: this.filterParams(filters),
        observe: 'response',
      })
      .pipe(
        map((res) => ({
          lineups: res.body ?? [],
          total: Number(res.headers.get('X-Total-Count') ?? res.body?.length ?? 0),
        })),
      );
  }

  getTrend(teamId: string, playerIds: string[], filters: ContextFilters = {}): Observable<TrendPoint[]> {
    return this.http.get<TrendPoint[]>(`${this.baseUrl}/lineups/trend`, {
      headers: this.headers,
      params: this.filterParams({ ...filters, team_id: teamId, player_ids: playerIds }),
    });
  }

  getPlayers(filters: PlayerFilters = {}): Observable<PlayersPage> {
    return this.http
      .get<PlayerOnOff[]>(`${this.baseUrl}/players`, {
        headers: this.headers,
        params: this.filterParams(filters),
        observe: 'response',
      })
      .pipe(
        map((res) => ({
          players: res.body ?? [],
          total: Number(res.headers.get('X-Total-Count') ?? res.body?.length ?? 0),
        })),
      );
  }

  getShots(
    filters: ContextFilters & { player_ids?: string[]; side: 'offense' | 'defense' },
  ): Observable<ShotChart> {
    return this.http.get<ShotChart>(`${this.baseUrl}/shots`, {
      headers: this.headers,
      params: this.filterParams(filters),
    });
  }

  getLeague(filters: ContextFilters = {}): Observable<LeagueAverages> {
    const { team_id: _team, location: _location, ...gameFilters } = filters;
    return this.http.get<LeagueAverages>(`${this.baseUrl}/league`, {
      headers: this.headers,
      params: this.filterParams(gameFilters),
    });
  }

  getMeta(): Observable<DatasetMeta> {
    return this.http.get<DatasetMeta>(`${this.baseUrl}/meta`, { headers: this.headers });
  }

  getTeams(): Observable<Team[]> {
    return this.http.get<Team[]>(`${this.baseUrl}/teams`, { headers: this.headers });
  }
}
