export interface LineupPlayer {
  player_id: string;
  name: string;
  position: string;
  height_in: number | null;
  weight_lb: number | null;
}

export type GameType = 'Regular Season' | 'Play-In' | 'Playoffs';
export type Location = 'home' | 'away';

/** Which part of the season counts. Shared by every endpoint. */
export interface ContextFilters {
  team_id?: string;
  game_type?: GameType | '';
  location?: Location | '';
  clutch?: boolean;
  period?: number;
  date_from?: string;
  date_to?: string;
}

export interface LineupFilters extends ContextFilters {
  lineup_size?: number;
  player_ids?: string[];
  exclude_player_ids?: string[];
  min_possessions?: number;
  game_id?: string;
  search?: string;
  sort_by?: string;
  order?: 'asc' | 'desc';
  limit?: number;
  offset?: number;
}

/** Raw possession sums for one side of the ball; keys are prefixed `offensive_` / `defensive_` in the API. */
export interface LineupSummary {
  team_id: string;
  team_name: string;
  team_abbreviation: string;
  player_ids: string[];
  players: LineupPlayer[];
  total_possessions: number;
  offensive_possessions: number;
  defensive_possessions: number;
  offensive_points: number;
  defensive_points: number;
  offensive_rating: number;
  defensive_rating: number;
  net_rating: number;
  offensive_ppp: number;
  defensive_ppp: number;
  offensive_efg_pct: number;
  defensive_efg_pct: number;
  offensive_ts_pct: number;
  defensive_ts_pct: number;
  offensive_turnover_rate: number;
  defensive_turnover_rate: number;
  offensive_ft_rate: number;
  defensive_ft_rate: number;
  offensive_fg3_rate: number;
  defensive_fg3_rate: number;
  offensive_assist_rate: number;
  oreb_pct: number;
  dreb_pct: number;
  total_reb_pct: number;
  opponent_oreb_pct: number;
  pace: number;
  minutes: number;
  games_played: number;
  avg_height_in: number;
  avg_weight_lb: number;
  guards: number;
  forwards: number;
  centers: number;
  // Remaining offensive_* / defensive_* counting stats, *_pct shooting splits and *_per100 scoring context.
  [stat: string]: unknown;
}

export interface LineupsPage {
  lineups: LineupSummary[];
  total: number;
}

export interface Team {
  team_id: string;
  name: string;
  city: string;
  nickname: string;
  abbreviation: string;
}

/** League-wide rates over the games the current filters cover (each possession counted once). */
export interface LeagueAverages {
  possessions: number;
  offensive_rating: number;
  fg2: number;
  fg3: number;
  ft: number;
  efg: number;
  oreb: number;
  dreb: number;
  turnover: number;
  ft_rate: number;
  fg3_rate: number;
  pace: number;
  // Zone and shot-type FG% (`ra`, `paint`, `dunk`, ...), their `_share` of attempts, and `*_per100` context.
  [stat: string]: number;
}

export interface TrendPoint {
  month: string;
  offensive_possessions: number;
  defensive_possessions: number;
  offensive_rating: number;
  defensive_rating: number;
  net_rating: number;
  minutes: number;
}

export interface SplitMetrics {
  offensive_rating: number;
  defensive_rating: number;
  net_rating: number;
  offensive_efg_pct: number;
  defensive_efg_pct: number;
  offensive_turnover_rate: number;
  defensive_turnover_rate: number;
  oreb_pct: number;
  dreb_pct: number;
  offensive_ft_rate: number;
  pace: number;
}

export interface PlayerOnOff {
  player_id: string;
  team_id: string;
  team_name: string;
  team_abbreviation: string;
  name: string;
  position: string;
  height_in: number | null;
  weight_lb: number | null;
  birth_date: string | null;
  country: string | null;
  school: string | null;
  draft_year: number | null;
  draft_round: number | null;
  draft_number: number | null;
  games: number;
  minutes_per_game: number;
  points_per_game: number;
  rebounds_per_game: number;
  assists_per_game: number;
  steals_per_game: number;
  blocks_per_game: number;
  possessions: number;
  minutes: number;
  games_played: number;
  off_possessions: number;
  off_minutes: number;
  share_of_team_possessions: number;
  on: SplitMetrics;
  off: SplitMetrics;
  on_off_net: number;
  on_off_offense: number;
  on_off_defense: number;
}

export interface PlayerFilters extends ContextFilters {
  player_ids?: string[];
  min_possessions?: number;
  search?: string;
  sort_by?: string;
  order?: 'asc' | 'desc';
  limit?: number;
  offset?: number;
}

export interface PlayersPage {
  players: PlayerOnOff[];
  total: number;
}

export type ShotZone = 'ra' | 'paint' | 'mid' | 'lc3' | 'rc3' | 'atb3';

export interface ShotSplit {
  label: string;
  attempted: number;
  made: number;
  pct: number;
  league_pct: number;
  vs_league: number;
  share: number;
  league_share: number;
  points_per_shot: number;
  zone?: ShotZone;
  shot_type?: string;
}

export interface ShotHex {
  x: number;
  y: number;
  attempted: number;
  made: number;
  pct: number;
  zone: ShotZone;
  vs_league: number;
}

export interface ShotChart {
  side: 'offense' | 'defense';
  attempted: number;
  made: number;
  hex_size: number;
  zones: ShotSplit[];
  shot_types: ShotSplit[];
  hexes: ShotHex[];
}

export interface DatasetMeta {
  season: string;
  source: string;
  first_game: string | null;
  last_game: string | null;
  games: Record<string, number>;
  possessions: number;
  shots: number;
  players: number;
  approximations: Record<string, string>;
  notes: string[];
}
