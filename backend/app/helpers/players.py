"""Helpers for the players API: each player's on-court numbers, his team's numbers without him, and his bio."""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Optional

import pandas as pd

from app.dbmodels.models import Player
from app.helpers.data import EXTRA_SUMMED_STATS, SUMMED_STATS, Filters, side_frames
from app.helpers.lineups import derived_metrics, lineup_table, ratio, team_lookup

PlayerRecord = dict[str, Any]

# The rates shown for each split: with the player on the floor, and his team's possessions without him.
SPLIT_METRICS = (
    'offensive_rating', 'defensive_rating', 'net_rating', 'offensive_efg_pct', 'defensive_efg_pct',
    'offensive_turnover_rate', 'defensive_turnover_rate', 'oreb_pct', 'dreb_pct', 'offensive_ft_rate', 'pace',
)

BIO_FIELDS = (
    'name', 'position', 'height_in', 'weight_lb', 'birth_date', 'country', 'school', 'draft_year', 'draft_round',
    'draft_number', 'games', 'minutes_per_game', 'points_per_game', 'rebounds_per_game', 'assists_per_game',
    'steals_per_game', 'blocks_per_game',
)

SORTABLE_FIELDS = frozenset(
    ['possessions', 'minutes', 'on_off_net', 'on_off_offense', 'on_off_defense']
    + [f'on_{metric}' for metric in SPLIT_METRICS]
    + [f'off_{metric}' for metric in SPLIT_METRICS]
    + ['points_per_game', 'rebounds_per_game', 'assists_per_game', 'height_in']
)

VALUE_COLUMNS = ('possessions', *SUMMED_STATS, *EXTRA_SUMMED_STATS)


def _team_totals(filters: Filters) -> pd.DataFrame:
    sides = []
    for side, frame in side_frames(filters).items():
        totals = frame.groupby('team_id')[list(VALUE_COLUMNS)].sum()
        totals.columns = [f'{side}_{column}' for column in totals.columns]
        sides.append(totals)
    return pd.concat(sides, axis=1).fillna(0)


@lru_cache(maxsize=1)
def _bios() -> pd.DataFrame:
    bios = pd.DataFrame.from_records(Player.objects.values('id', *BIO_FIELDS), index='id')
    bios['birth_date'] = bios['birth_date'].astype(str).where(bios['birth_date'].notna(), None)
    return bios


@lru_cache(maxsize=24)
def on_off_table(filters: Filters) -> pd.DataFrame:
    """One row per (team, player): on-court sums and metrics, the same for his team with him off, and the gaps."""
    on = lineup_table(filters, 1)
    if on.empty:
        return pd.DataFrame()
    on = on.rename(columns={'k0': 'player_id'})
    sum_columns = [f'{side}_{column}' for side in ('offensive', 'defensive') for column in VALUE_COLUMNS]

    team = _team_totals(filters).reindex(on['team_id']).reset_index(drop=True)[sum_columns]
    off = team.to_numpy() - on[sum_columns].to_numpy()
    off = pd.DataFrame(off, columns=sum_columns, index=on.index).clip(lower=0)

    off_metrics = derived_metrics(off)
    table = pd.DataFrame({'team_id': on['team_id'], 'player_id': on['player_id']})
    table['possessions'] = on['total_possessions']
    table['minutes'] = on['minutes']
    table['games_played'] = on['games_played']
    table['off_possessions'] = off['offensive_possessions'] + off['defensive_possessions']
    table['off_minutes'] = ((off['offensive_seconds'] + off['defensive_seconds']) / 60).round(2)
    for metric in SPLIT_METRICS:
        table[f'on_{metric}'] = on[metric]
        table[f'off_{metric}'] = off_metrics[metric]
    has_off = table['off_possessions'] > 0
    table['on_off_net'] = (table['on_net_rating'] - table['off_net_rating']).where(has_off, 0).round(2)
    table['on_off_offense'] = (table['on_offensive_rating'] - table['off_offensive_rating']).where(has_off, 0).round(2)
    # For defense a drop in points allowed is the good direction, so the sign is flipped.
    table['on_off_defense'] = (table['off_defensive_rating'] - table['on_defensive_rating']).where(has_off, 0).round(2)
    table['share_of_team_possessions'] = ratio(
        table['possessions'], table['possessions'] + table['off_possessions'],
    )

    bios = _bios()
    for column in ('points_per_game', 'rebounds_per_game', 'assists_per_game', 'height_in'):
        table[column] = table['player_id'].map(bios[column]).fillna(0) if not bios.empty else 0
    return table


def _split(row: pd.Series, prefix: str) -> dict[str, float]:
    return {metric: float(row[f'{prefix}_{metric}']) for metric in SPLIT_METRICS}


def _record(row: pd.Series) -> PlayerRecord:
    bios = _bios()
    teams = team_lookup()
    player_id = int(row['player_id'])
    team_id = int(row['team_id'])
    bio = bios.loc[player_id] if player_id in bios.index else None
    record: PlayerRecord = {
        'player_id': str(player_id),
        'team_id': str(team_id),
        'team_name': teams.get(team_id, {}).get('name', ''),
        'team_abbreviation': teams.get(team_id, {}).get('abbreviation', ''),
        'possessions': int(row['possessions']),
        'minutes': float(row['minutes']),
        'games_played': int(row['games_played']),
        'off_possessions': int(row['off_possessions']),
        'off_minutes': float(row['off_minutes']),
        'share_of_team_possessions': float(row['share_of_team_possessions']),
        'on': _split(row, 'on'),
        'off': _split(row, 'off'),
        'on_off_net': float(row['on_off_net']),
        'on_off_offense': float(row['on_off_offense']),
        'on_off_defense': float(row['on_off_defense']),
    }
    for field in BIO_FIELDS:
        value = None if bio is None else bio[field]
        if value is not None and pd.isna(value):
            value = None
        if hasattr(value, 'item'):
            value = value.item()
        record[field] = value
    return record


def get_player_on_off_stats(
    team_id: Optional[str] = None,
    player_ids: Optional[list[str]] = None,
    min_possessions: int = 0,
    game_type: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    period: Optional[int] = None,
    clutch: bool = False,
    location: Optional[str] = None,
    search: str = '',
    sort_by: str = 'on_off_net',
    order: str = 'desc',
    limit: Optional[int] = None,
    offset: int = 0,
) -> tuple[list[PlayerRecord], int]:
    """Every player's on/off splits plus the total row count before pagination.

    "Off" is his team's possessions in the same filtered games with him on the bench, so on minus off isolates
    how the team plays with him compared to without him.
    """
    if sort_by not in SORTABLE_FIELDS:
        raise ValueError(f'Unknown sort_by "{sort_by}"')
    if order not in ('asc', 'desc'):
        raise ValueError('order must be "asc" or "desc"')

    filters = Filters(
        team_id=int(team_id) if team_id else None, game_type=game_type, date_from=date_from, date_to=date_to,
        period=period, clutch=clutch, location=location,
    )
    table = on_off_table(filters)
    if table.empty:
        return [], 0

    mask = table['possessions'] >= min_possessions
    if player_ids:
        mask &= table['player_id'].isin([int(player_id) for player_id in player_ids])
    query = search.strip().lower()
    if query:
        bios = _bios()
        matches = bios.index[bios['name'].str.lower().str.contains(query, regex=False)] if not bios.empty else []
        mask &= table['player_id'].isin(matches)
    rows = table[mask].sort_values([sort_by, 'player_id'], ascending=[order == 'asc', True])
    total = len(rows)
    end = None if limit is None else offset + limit
    return [_record(row) for _, row in rows.iloc[offset:end].iterrows()], total
