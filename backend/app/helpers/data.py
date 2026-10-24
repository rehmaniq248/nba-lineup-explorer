"""In-memory copies of the possession and shot data, plus the filters every endpoint shares.

A season is about 260k possessions and 230k shots: too many to sum row by row in Python on every request, and at
~350 MB too big for a small hosted Postgres. So they are read once from the compressed files that
scripts/build_dataset.py writes (raw_data/possessions.csv.gz and shots.csv.gz, ~5 MB together), joined to the
games table for dates and game types, and aggregated with pandas.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

import pandas as pd
from django.conf import settings

from app.dbmodels.models import Game

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


def _data_file(name: str) -> Path:
    return Path(settings.RAW_DATA_DIR) / name


def _split_players(frame: pd.DataFrame, column: str, names: tuple[str, ...]) -> pd.DataFrame:
    players = frame.pop(column).astype(str).str.split(';', expand=True).astype('int64')
    players.columns = list(names)
    return pd.concat([frame, players], axis=1)


def _games() -> pd.DataFrame:
    games = pd.DataFrame.from_records(
        Game.objects.values('id', 'date', 'game_type', 'home_team_id'),
        columns=['id', 'date', 'game_type', 'home_team_id'],
    )
    games['date'] = games['date'].astype(str)
    return games.rename(columns={'id': 'game_id'})


def _with_games(frame: pd.DataFrame) -> pd.DataFrame:
    """Attach each row's date and game type. Rows for games missing from the database are dropped."""
    return frame.merge(_games(), on='game_id', how='inner')


@lru_cache(maxsize=1)
def possessions() -> pd.DataFrame:
    frame = _with_games(pd.read_csv(_data_file('possessions.csv.gz')))
    frame = frame.drop(columns=['home_team_id'])
    frame['offense_is_home'] = frame['offense_is_home'].astype(bool)
    frame['clutch'] = frame['clutch'].astype(bool)
    frame = _split_players(frame, 'offensive_player_ids', OFFENSE_PLAYERS)
    frame = _split_players(frame, 'defensive_player_ids', DEFENSE_PLAYERS)
    frame['month'] = frame['date'].str[:7]
    frame['possessions'] = 1
    for stat in SUMMED_STATS:
        frame[stat] = frame[stat].astype('int32')
    return frame


@lru_cache(maxsize=1)
def shots() -> pd.DataFrame:
    frame = _with_games(pd.read_csv(_data_file('shots.csv.gz'), dtype={'zone': str, 'shot_type': str}))
    frame['clutch'] = frame['clutch'].astype(bool)
    frame['made'] = frame['made'].astype(bool)
    frame['offense_is_home'] = frame.pop('home_team_id') == frame['offensive_team_id']
    frame = _split_players(frame, 'offensive_player_ids', OFFENSE_PLAYERS)
    return _split_players(frame, 'defensive_player_ids', DEFENSE_PLAYERS)


def clear_cache() -> None:
    """Drop every cached frame and aggregate, e.g. after rebuilding the data or between tests."""
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
