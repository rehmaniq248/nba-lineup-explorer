"""In-memory copies of the possession and shot tables, plus the filters every endpoint shares.

A season is about 260k possessions, too many to sum row by row in Python on every request, so each table is
pulled out of Postgres once with COPY and aggregated with pandas.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional

import pandas as pd
from django.db import connection

SIDES = ('offensive', 'defensive')

# Possession-level counting stats that are summed per lineup, per side. The first block mirrors the original
# possession contract; the rest are new to the NBA dataset.
SUMMED_STATS = (
    'points',
    'shot_attempts',
    'fg2_made',
    'fg2_attempted',
    'fg3_made',
    'fg3_attempted',
    'fg_made',
    'fg_attempted',
    'ft_made',
    'ft_attempted',
    'rebounds_offense',
    'rebounds_defense',
    'rebound_opportunities',
    'assists',
    'steals',
    'turnovers',
    'blocks',
    'offensive_fouls',
    'defensive_fouls',
    'shooting_fouls',
    'shot_attempt_points',
    'ft_potential_points',
    'transition_take_fouls',
    'ra_made',
    'ra_attempted',
    'paint_made',
    'paint_attempted',
    'mid_made',
    'mid_attempted',
    'corner3_made',
    'corner3_attempted',
    'atb3_made',
    'atb3_attempted',
    'dunk_made',
    'dunk_attempted',
    'layup_made',
    'layup_attempted',
    'jumper_made',
    'jumper_attempted',
    'hook_made',
    'hook_attempted',
    'paint_points',
    'fastbreak_points',
    'second_chance_points',
    'points_off_turnovers',
)
# Summed too, but not part of the response contract.
EXTRA_SUMMED_STATS = ('seconds',)

SHOT_ZONES = ('ra', 'paint', 'mid', 'corner3', 'atb3')
SHOT_TYPES = ('dunk', 'layup', 'hook', 'jumper')
CONTEXT_POINTS = ('paint_points', 'fastbreak_points', 'second_chance_points', 'points_off_turnovers')

APPROXIMATIONS = {
    'shot_attempt_points': (
        'Approximation. Points from made field goals plus the and-one free throw that came with them. The '
        'play-by-play has no direct equivalent of this stat.'
    ),
    'ft_potential_points': (
        'Approximation. One potential point per free throw attempted (technical free throws excluded).'
    ),
}

GAME_TYPES = ('Regular Season', 'Play-In', 'Playoffs')
LOCATIONS = ('home', 'away')

OFFENSE_PLAYERS = tuple(f'o{index}' for index in range(5))
DEFENSE_PLAYERS = tuple(f'd{index}' for index in range(5))


@dataclass(frozen=True)
class Filters:
    """Which possessions count. Hashable so aggregated results can be cached per filter set."""

    team_id: Optional[int] = None
    game_type: Optional[str] = None
    game_id: Optional[int] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    period: Optional[int] = None
    clutch: bool = False
    location: Optional[str] = None


def _copy_frame(sql: str) -> pd.DataFrame:
    buffer = io.StringIO()
    with connection.cursor() as cursor:
        cursor.copy_expert(f'COPY ({sql}) TO STDOUT WITH CSV HEADER', buffer)
    buffer.seek(0)
    return pd.read_csv(buffer)


def _split_players(frame: pd.DataFrame, column: str, names: tuple[str, ...]) -> pd.DataFrame:
    players = frame.pop(column).str.strip('{}').str.split(',', expand=True).astype('int64')
    players.columns = list(names)
    return pd.concat([frame, players], axis=1)


def _bools(frame: pd.DataFrame, *columns: str) -> None:
    for column in columns:
        frame[column] = frame[column] == 't'


@lru_cache(maxsize=1)
def possessions() -> pd.DataFrame:
    stats = ', '.join(f'p.{stat}' for stat in (*SUMMED_STATS, *EXTRA_SUMMED_STATS))
    frame = _copy_frame(
        'SELECT p.game_id, g.date, g.game_type, p.period, p.offensive_team_id, p.defensive_team_id, '
        f'p.offensive_player_ids, p.defensive_player_ids, p.offense_is_home, p.clutch, {stats} '
        'FROM possession p JOIN game g ON g.id = p.game_id'
    )
    _bools(frame, 'offense_is_home', 'clutch')
    frame = _split_players(frame, 'offensive_player_ids', OFFENSE_PLAYERS)
    frame = _split_players(frame, 'defensive_player_ids', DEFENSE_PLAYERS)
    frame['month'] = frame['date'].str[:7]
    frame['possessions'] = 1
    for stat in SUMMED_STATS:
        frame[stat] = frame[stat].astype('int32')
    return frame


@lru_cache(maxsize=1)
def shots() -> pd.DataFrame:
    frame = _copy_frame(
        'SELECT s.game_id, g.date, g.game_type, s.period, s.clutch, s.offensive_team_id, s.defensive_team_id, '
        's.offensive_player_ids, s.defensive_player_ids, s.shooter_id, s.x, s.y, s.zone, s.shot_type, s.value, '
        's.made, g.home_team_id FROM shot s JOIN game g ON g.id = s.game_id'
    )
    _bools(frame, 'clutch', 'made')
    frame['offense_is_home'] = frame.pop('home_team_id') == frame['offensive_team_id']
    frame = _split_players(frame, 'offensive_player_ids', OFFENSE_PLAYERS)
    return _split_players(frame, 'defensive_player_ids', DEFENSE_PLAYERS)


def clear_cache() -> None:
    """Drop every cached frame and aggregate, e.g. after re-ingesting or between tests."""
    from app.helpers import lineups, players, shots as shot_helpers

    possessions.cache_clear()
    shots.cache_clear()
    for module in (lineups, players, shot_helpers):
        for function in vars(module).values():
            if hasattr(function, 'cache_clear'):
                function.cache_clear()


def game_mask(frame: pd.DataFrame, filters: Filters) -> pd.Series:
    """Filters that apply to a whole possession, whichever side of the ball a lineup is on."""
    mask = pd.Series(True, index=frame.index)
    if filters.game_type:
        mask &= frame['game_type'] == filters.game_type
    if filters.game_id:
        mask &= frame['game_id'] == filters.game_id
    if filters.date_from:
        mask &= frame['date'] >= filters.date_from
    if filters.date_to:
        mask &= frame['date'] <= filters.date_to
    if filters.period:
        # Every overtime period is grouped under period 5.
        mask &= frame['period'] >= 5 if filters.period >= 5 else frame['period'] == filters.period
    if filters.clutch:
        mask &= frame['clutch']
    return mask


def side_mask(frame: pd.DataFrame, filters: Filters, side: str) -> pd.Series:
    """Filters that depend on which team the lineup belongs to: its team and whether it was at home."""
    team_column = 'offensive_team_id' if side == 'offensive' else 'defensive_team_id'
    mask = pd.Series(True, index=frame.index)
    if filters.team_id:
        mask &= frame[team_column] == filters.team_id
    if filters.location:
        at_home = frame['offense_is_home'] if side == 'offensive' else ~frame['offense_is_home']
        mask &= at_home if filters.location == 'home' else ~at_home
    return mask


def side_frames(filters: Filters, frame: Optional[pd.DataFrame] = None) -> dict[str, pd.DataFrame]:
    """Possessions seen from each side, with the lineup's team in `team_id` and its players in p0..p4."""
    frame = possessions() if frame is None else frame
    base = game_mask(frame, filters)
    sides = {}
    for side, team_column, player_columns in (
        ('offensive', 'offensive_team_id', OFFENSE_PLAYERS),
        ('defensive', 'defensive_team_id', DEFENSE_PLAYERS),
    ):
        rows = frame[base & side_mask(frame, filters, side)]
        renamed = {team_column: 'team_id', **{column: f'p{index}' for index, column in enumerate(player_columns)}}
        sides[side] = rows.rename(columns=renamed)
    return sides


def contains_players(frame: pd.DataFrame, player_ids: tuple[int, ...], columns: tuple[str, ...]) -> pd.Series:
    """Rows whose five players include every one of `player_ids`."""
    mask = pd.Series(True, index=frame.index)
    for player_id in player_ids:
        mask &= frame[list(columns)].eq(player_id).any(axis=1)
    return mask
