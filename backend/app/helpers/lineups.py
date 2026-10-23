from __future__ import annotations

"""Helpers for the lineup summary API."""

from functools import lru_cache
from itertools import combinations
from typing import Any, Optional

import numpy as np
import pandas as pd

from app.dbmodels.models import Player, Team
from app.helpers.data import (
    CONTEXT_POINTS, EXTRA_SUMMED_STATS, SHOT_TYPES, SHOT_ZONES, SIDES, SUMMED_STATS, Filters, contains_players,
    side_frames,
)

LineupRecord = dict[str, Any]

DERIVED_METRICS = (
    'offensive_rating',
    'defensive_rating',
    'net_rating',
    'offensive_ppp',
    'defensive_ppp',
    'offensive_efg_pct',
    'defensive_efg_pct',
    'offensive_ts_pct',
    'defensive_ts_pct',
    'offensive_turnover_rate',
    'defensive_turnover_rate',
    'offensive_ft_rate',
    'defensive_ft_rate',
    'offensive_assist_rate',
    'offensive_fg3_rate',
    'defensive_fg3_rate',
    'oreb_pct',
    'dreb_pct',
    'total_reb_pct',
    'opponent_oreb_pct',
    'pace',
    'minutes',
    'games_played',
    *(f'{side}_{context}_per100' for side in SIDES for context in CONTEXT_POINTS),
)

SHOT_PCT_GROUPS = ('fg', 'fg2', 'fg3', *SHOT_ZONES, *SHOT_TYPES)
LINEUP_PROFILE = ('avg_height_in', 'avg_weight_lb', 'guards', 'forwards', 'centers')

VALUE_COLUMNS = ('possessions', *SUMMED_STATS, *EXTRA_SUMMED_STATS)


def _sum_fields(side: str) -> list[str]:
    return [f'{side}_{stat}' for stat in SUMMED_STATS]


SORTABLE_FIELDS = frozenset(
    ['offensive_possessions', 'defensive_possessions', 'total_possessions']
    + _sum_fields('offensive')
    + _sum_fields('defensive')
    + list(DERIVED_METRICS)
    + [f'{side}_{shot}_pct' for side in SIDES for shot in SHOT_PCT_GROUPS]
    + list(LINEUP_PROFILE)
)


def _normalize_lineup_size(lineup_size: Any) -> int:
    try:
        normalized_lineup_size = int(lineup_size)
    except (TypeError, ValueError):
        return 5

    return max(1, min(5, normalized_lineup_size))


def ratio(numerator, denominator, digits: int = 4):
    """numerator / denominator, 0 where the denominator is 0. Works on scalars and Series alike."""
    numerator = np.asarray(numerator, dtype='float64')
    denominator = np.asarray(denominator, dtype='float64')
    with np.errstate(divide='ignore', invalid='ignore'):
        values = np.where(denominator > 0, numerator / np.where(denominator > 0, denominator, 1), 0.0)
    return np.round(values, digits)


def derived_metrics(table: pd.DataFrame) -> pd.DataFrame:
    """Ratings and rates computed from `offensive_*` / `defensive_*` sums. Shared with the players endpoint."""
    off_poss = table['offensive_possessions']
    def_poss = table['defensive_possessions']
    metrics = pd.DataFrame(index=table.index)
    metrics['offensive_rating'] = ratio(100 * table['offensive_points'], off_poss, 2)
    metrics['defensive_rating'] = ratio(100 * table['defensive_points'], def_poss, 2)
    metrics['offensive_ppp'] = ratio(table['offensive_points'], off_poss)
    metrics['defensive_ppp'] = ratio(table['defensive_points'], def_poss)
    # Net rating only means something once the lineup has been on the floor for both sides of the ball.
    both = (off_poss > 0) & (def_poss > 0)
    metrics['net_rating'] = np.where(both, (metrics['offensive_rating'] - metrics['defensive_rating']).round(2), 0)

    for side, poss in (('offensive', off_poss), ('defensive', def_poss)):
        fga = table[f'{side}_fg_attempted']
        fta = table[f'{side}_ft_attempted']
        metrics[f'{side}_efg_pct'] = ratio(table[f'{side}_fg_made'] + 0.5 * table[f'{side}_fg3_made'], fga)
        metrics[f'{side}_ts_pct'] = ratio(table[f'{side}_points'], 2 * (fga + 0.44 * fta))
        metrics[f'{side}_turnover_rate'] = ratio(table[f'{side}_turnovers'], poss)
        metrics[f'{side}_ft_rate'] = ratio(fta, fga)
        metrics[f'{side}_fg3_rate'] = ratio(table[f'{side}_fg3_attempted'], fga)
        for context in CONTEXT_POINTS:
            metrics[f'{side}_{context}_per100'] = ratio(100 * table[f'{side}_{context}'], poss, 2)
    metrics['offensive_assist_rate'] = ratio(table['offensive_assists'], table['offensive_fg_made'])

    # A possession's rebounds_offense is credited to its offense and rebounds_defense to its defense, and the two
    # sum to rebound_opportunities, so each side of the lineup owns one rebound column.
    off_opps = table['offensive_rebound_opportunities']
    def_opps = table['defensive_rebound_opportunities']
    metrics['oreb_pct'] = ratio(table['offensive_rebounds_offense'], off_opps)
    metrics['dreb_pct'] = ratio(table['defensive_rebounds_defense'], def_opps)
    metrics['opponent_oreb_pct'] = ratio(table['defensive_rebounds_offense'], def_opps)
    metrics['total_reb_pct'] = ratio(
        table['offensive_rebounds_offense'] + table['defensive_rebounds_defense'], off_opps + def_opps,
    )

    seconds = table['offensive_seconds'] + table['defensive_seconds']
    metrics['minutes'] = (seconds / 60).round(2)
    # Possessions per 48 minutes, counting both teams' possessions as the NBA does, halved.
    metrics['pace'] = ratio(48 * 60 * (off_poss + def_poss) / 2, seconds, 1)
    return metrics


def shooting_pct_fields(table: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({
        f'{side}_{shot}_pct': ratio(table[f'{side}_{shot}_made'], table[f'{side}_{shot}_attempted'])
        for side in SIDES
        for shot in SHOT_PCT_GROUPS
    }, index=table.index)


@lru_cache(maxsize=48)
def lineup_table(filters: Filters, lineup_size: int) -> pd.DataFrame:
    """Every `lineup_size`-man lineup's sums for both sides of the ball, one row per (team, players).

    Every possession contributes to the lineups of both teams on the floor: once to the offensive team's
    lineups (``offensive_*`` columns) and once to the defensive team's lineups (``defensive_*`` columns).
    """
    keys = [f'k{index}' for index in range(lineup_size)]
    sums, appearances = [], []
    for side, frame in side_frames(filters).items():
        players = [f'p{index}' for index in range(5)]
        # Collapse to unique five-man units first, so the combinations below stay small.
        by_unit = frame.groupby(['team_id', *players], sort=False)[list(VALUE_COLUMNS)].sum()
        by_unit.columns = [f'{side}_{column}' for column in by_unit.columns]
        by_unit = by_unit.reset_index()
        unit_games = frame[['team_id', *players, 'game_id']].drop_duplicates()
        for combo in combinations(range(5), lineup_size):
            rename = {f'p{position}': key for position, key in zip(combo, keys)}
            sums.append(by_unit.drop(columns=[p for p in players if p not in rename]).rename(columns=rename))
            appearances.append(unit_games[['team_id', *rename, 'game_id']].rename(columns=rename))

    if not sums:
        return pd.DataFrame()
    table = pd.concat(sums, ignore_index=True).fillna(0).groupby(['team_id', *keys], sort=False).sum()
    games = pd.concat(appearances, ignore_index=True).drop_duplicates().groupby(['team_id', *keys]).size()
    table['games_played'] = games.reindex(table.index).fillna(0).astype(int)
    table = table.reset_index()
    for side in SIDES:
        for column in VALUE_COLUMNS:
            name = f'{side}_{column}'
            if name not in table:
                table[name] = 0
    table['total_possessions'] = table['offensive_possessions'] + table['defensive_possessions']
    table = pd.concat([table, derived_metrics(table), shooting_pct_fields(table)], axis=1)
    return pd.concat([table, _lineup_profile(table, keys)], axis=1)


@lru_cache(maxsize=1)
def player_bios() -> pd.DataFrame:
    bios = pd.DataFrame.from_records(
        Player.objects.values('id', 'name', 'position', 'height_in', 'weight_lb'), index='id',
    )
    for column in ('height_in', 'weight_lb'):
        if column in bios:
            bios[column] = pd.to_numeric(bios[column], errors='coerce')
    return bios


@lru_cache(maxsize=1)
def team_lookup() -> dict[int, dict[str, str]]:
    return {
        team['id']: {'name': team['name'], 'abbreviation': team['abbreviation']}
        for team in Team.objects.values('id', 'name', 'abbreviation')
    }


def _lineup_profile(table: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    """Size and positional makeup: average height and weight, and how many players list each position."""
    bios = player_bios()
    profile = pd.DataFrame(index=table.index)
    if bios.empty:
        for column in LINEUP_PROFILE:
            profile[column] = 0
        return profile
    heights = pd.concat([table[key].map(bios['height_in']) for key in keys], axis=1)
    weights = pd.concat([table[key].map(bios['weight_lb']) for key in keys], axis=1)
    positions = pd.concat([table[key].map(bios['position']).fillna('') for key in keys], axis=1)
    profile['avg_height_in'] = heights.mean(axis=1).round(1).fillna(0)
    profile['avg_weight_lb'] = weights.mean(axis=1).round(1).fillna(0)
    for column, letter in (('guards', 'G'), ('forwards', 'F'), ('centers', 'C')):
        profile[column] = positions.apply(lambda col: col.str.contains(letter)).sum(axis=1)
    return profile


def _matching_player_ids(search: str) -> set[int]:
    query = search.strip().lower()
    bios = player_bios()
    if not query or bios.empty:
        return set()
    return set(bios.index[bios['name'].str.lower().str.contains(query, regex=False)])


def _build_record(row: pd.Series, keys: list[str]) -> LineupRecord:
    bios = player_bios()
    teams = team_lookup()
    record: LineupRecord = {}
    for side in SIDES:
        record[f'{side}_possessions'] = int(row[f'{side}_possessions'])
        for stat in SUMMED_STATS:
            record[f'{side}_{stat}'] = int(row[f'{side}_{stat}'])
    record['total_possessions'] = int(row['total_possessions'])
    for side in SIDES:
        for shot in SHOT_PCT_GROUPS:
            record[f'{side}_{shot}_pct'] = float(row[f'{side}_{shot}_pct'])
    team_id = int(row['team_id'])
    record['team_id'] = str(team_id)
    record['team_name'] = teams.get(team_id, {}).get('name', '')
    record['team_abbreviation'] = teams.get(team_id, {}).get('abbreviation', '')
    player_ids = sorted(int(row[key]) for key in keys)
    record['player_ids'] = [str(player_id) for player_id in player_ids]
    record['players'] = [_player(player_id, bios) for player_id in player_ids]
    for metric in DERIVED_METRICS:
        value = row[metric]
        record[metric] = int(value) if metric == 'games_played' else float(value)
    for column in LINEUP_PROFILE:
        record[column] = float(row[column])
    return record


def _player(player_id: int, bios: pd.DataFrame) -> dict[str, Any]:
    if player_id not in bios.index:
        return {'player_id': str(player_id), 'name': '', 'position': '', 'height_in': None, 'weight_lb': None}
    bio = bios.loc[player_id]
    return {
        'player_id': str(player_id),
        'name': bio['name'],
        'position': bio['position'],
        'height_in': None if pd.isna(bio['height_in']) else int(bio['height_in']),
        'weight_lb': None if pd.isna(bio['weight_lb']) else int(bio['weight_lb']),
    }


def get_lineup_league_summary_stats(
    lineup_size: int = 5,
    team_id: Optional[str] = None,
    player_ids: Optional[list[str]] = None,
    exclude_player_ids: Optional[list[str]] = None,
    min_possessions: int = 0,
    game_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    period: Optional[int] = None,
    game_type: Optional[str] = None,
    clutch: bool = False,
    location: Optional[str] = None,
    search: str = '',
    sort_by: str = 'net_rating',
    order: str = 'desc',
    limit: Optional[int] = None,
    offset: int = 0,
) -> tuple[list[LineupRecord], int]:
    """Return lineup summaries across the league plus the total row count before pagination."""
    if sort_by not in SORTABLE_FIELDS:
        raise ValueError(f'Unknown sort_by "{sort_by}"')
    if order not in ('asc', 'desc'):
        raise ValueError('order must be "asc" or "desc"')

    lineup_size = _normalize_lineup_size(lineup_size)
    keys = [f'k{index}' for index in range(lineup_size)]
    filters = Filters(
        team_id=int(team_id) if team_id else None, game_type=game_type, game_id=int(game_id) if game_id else None,
        date_from=date_from, date_to=date_to, period=period, clutch=clutch, location=location,
    )
    table = lineup_table(filters, lineup_size)
    if table.empty:
        return [], 0

    mask = table['total_possessions'] >= min_possessions
    members = table[keys]
    for player_id in player_ids or []:
        mask &= members.eq(int(player_id)).any(axis=1)
    excluded = [int(player_id) for player_id in exclude_player_ids or []]
    if excluded:
        mask &= ~members.isin(excluded).any(axis=1)
    if search.strip():
        mask &= members.isin(_matching_player_ids(search)).any(axis=1)
    rows = table[mask]

    # Secondary keys keep the ordering stable across identical sort values.
    rows = rows.sort_values([sort_by, 'team_id', *keys], ascending=[order == 'asc', True, *[True] * len(keys)])
    total = len(rows)
    end = None if limit is None else offset + limit
    return [_build_record(row, keys) for _, row in rows.iloc[offset:end].iterrows()], total


def get_lineup_trend(
    player_ids: list[str], team_id: str, filters: Optional[Filters] = None,
) -> list[dict[str, Any]]:
    """Month-by-month possessions and ratings for one lineup: every possession all of `player_ids` shared."""
    filters = filters or Filters()
    ids = tuple(int(player_id) for player_id in player_ids)
    months: dict[str, dict[str, Any]] = {}
    scoped = Filters(**{**filters.__dict__, 'team_id': int(team_id)})
    for side, frame in side_frames(scoped).items():
        rows = frame[contains_players(frame, ids, tuple(f'p{index}' for index in range(5)))]
        grouped = rows.groupby('month')[['possessions', 'points', 'seconds']].sum()
        for month, values in grouped.iterrows():
            entry = months.setdefault(month, {'month': month})
            entry[f'{side}_possessions'] = int(values['possessions'])
            entry[f'{side}_points'] = int(values['points'])
            entry[f'{side}_seconds'] = float(values['seconds'])
    trend = []
    for month in sorted(months):
        entry = months[month]
        off_poss = entry.get('offensive_possessions', 0)
        def_poss = entry.get('defensive_possessions', 0)
        off_rating = float(ratio(100 * entry.get('offensive_points', 0), off_poss, 2))
        def_rating = float(ratio(100 * entry.get('defensive_points', 0), def_poss, 2))
        trend.append({
            'month': month,
            'offensive_possessions': off_poss,
            'defensive_possessions': def_poss,
            'offensive_rating': off_rating,
            'defensive_rating': def_rating,
            'net_rating': round(off_rating - def_rating, 2) if off_poss and def_poss else 0,
            'minutes': round((entry.get('offensive_seconds', 0) + entry.get('defensive_seconds', 0)) / 60, 1),
        })
    return trend
