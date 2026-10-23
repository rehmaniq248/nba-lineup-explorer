"""Helpers for the shots API: where a lineup (or its opponents) shot from, binned for a half-court chart."""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Optional

import numpy as np
import pandas as pd

from app.helpers.data import DEFENSE_PLAYERS, OFFENSE_PLAYERS, Filters, contains_players, game_mask, shots
from app.helpers.lineups import ratio

ZONES = ('ra', 'paint', 'mid', 'lc3', 'rc3', 'atb3')
ZONE_LABELS = {
    'ra': 'Restricted area',
    'paint': 'Paint (non-RA)',
    'mid': 'Mid-range',
    'lc3': 'Left corner 3',
    'rc3': 'Right corner 3',
    'atb3': 'Above the break 3',
}
SHOT_TYPES = ('dunk', 'layup', 'hook', 'jumper')
SHOT_TYPE_LABELS = {'dunk': 'Dunk', 'layup': 'Layup', 'hook': 'Hook', 'jumper': 'Jump shot'}

# Hexagon "radius" in feet. Shots past half court are left off the chart.
HEX_SIZE = 1.6
HALF_COURT_DEPTH = 47


def _hex_centers(x: np.ndarray, y: np.ndarray, size: float) -> tuple[np.ndarray, np.ndarray]:
    """Snap points to the centres of a pointy-top hexagon grid (cube-coordinate rounding)."""
    q = (np.sqrt(3) / 3 * x - y / 3) / size
    r = (2 / 3 * y) / size
    cx, cz = q, r
    cy = -cx - cz
    rx, ry, rz = np.round(cx), np.round(cy), np.round(cz)
    dx, dy, dz = np.abs(rx - cx), np.abs(ry - cy), np.abs(rz - cz)
    fix_x = (dx > dy) & (dx > dz)
    fix_z = ~fix_x & (dz >= dy)
    rx = np.where(fix_x, -ry - rz, rx)
    rz = np.where(fix_z, -rx - ry, rz)
    return size * np.sqrt(3) * (rx + rz / 2), size * 1.5 * rz


def _zone_split(frame: pd.DataFrame, column: str, keys: tuple[str, ...]) -> pd.DataFrame:
    grouped = frame.groupby(column).agg(attempted=('made', 'size'), made=('made', 'sum'), value=('value', 'sum'))
    points = frame[frame['made']].groupby(column)['value'].sum()
    grouped = grouped.reindex(list(keys)).fillna(0)
    grouped['points'] = points.reindex(list(keys)).fillna(0)
    return grouped


@lru_cache(maxsize=8)
def _league(filters: Filters) -> dict[str, pd.DataFrame]:
    frame = shots()
    rows = frame[game_mask(frame, filters)]
    return {'zones': _zone_split(rows, 'zone', ZONES), 'types': _zone_split(rows, 'shot_type', SHOT_TYPES)}


def _split_records(split: pd.DataFrame, league: pd.DataFrame, labels: dict[str, str], key_name: str) -> list[dict]:
    total = split['attempted'].sum()
    records = []
    for key, row in split.iterrows():
        league_row = league.loc[key]
        pct = float(ratio(row['made'], row['attempted']))
        league_pct = float(ratio(league_row['made'], league_row['attempted']))
        records.append({
            key_name: key,
            'label': labels[key],
            'attempted': int(row['attempted']),
            'made': int(row['made']),
            'pct': pct,
            'league_pct': league_pct,
            'vs_league': round(pct - league_pct, 4) if row['attempted'] else 0,
            'share': float(ratio(row['attempted'], total)),
            'league_share': float(ratio(league_row['attempted'], league['attempted'].sum())),
            'points_per_shot': float(ratio(row['points'], row['attempted'], 3)),
        })
    return records


def get_shot_chart(
    player_ids: Optional[list[str]] = None,
    team_id: Optional[str] = None,
    side: str = 'offense',
    game_type: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    period: Optional[int] = None,
    clutch: bool = False,
    location: Optional[str] = None,
) -> dict[str, Any]:
    """Shots taken by a lineup (`side='offense'`) or by its opponents (`side='defense'`).

    A lineup is every shot where all of `player_ids` were on the floor for `team_id`. With no players it is the
    whole team, and with no team the whole league.
    """
    if side not in ('offense', 'defense'):
        raise ValueError('side must be "offense" or "defense"')
    filters = Filters(game_type=game_type, date_from=date_from, date_to=date_to, period=period, clutch=clutch)
    frame = shots()
    mask = game_mask(frame, filters)
    team_column = 'offensive_team_id' if side == 'offense' else 'defensive_team_id'
    players = OFFENSE_PLAYERS if side == 'offense' else DEFENSE_PLAYERS
    if team_id:
        mask &= frame[team_column] == int(team_id)
    if location:
        at_home = frame['offense_is_home'] if side == 'offense' else ~frame['offense_is_home']
        mask &= at_home if location == 'home' else ~at_home
    rows = frame[mask]
    if player_ids:
        rows = rows[contains_players(rows, tuple(int(player_id) for player_id in player_ids), players)]

    league = _league(filters)
    chart = rows[rows['y'] <= HALF_COURT_DEPTH]
    hex_x, hex_y = _hex_centers(chart['x'].to_numpy(), chart['y'].to_numpy(), HEX_SIZE)
    hexes = (
        pd.DataFrame({'x': hex_x.round(2), 'y': hex_y.round(2), 'made': chart['made'].to_numpy(),
                      'zone': chart['zone'].to_numpy()})
        .groupby(['x', 'y'])
        .agg(attempted=('made', 'size'), made=('made', 'sum'), zone=('zone', lambda zones: zones.mode()[0]))
        .reset_index()
    )
    league_zone_pct = (league['zones']['made'] / league['zones']['attempted'].replace(0, np.nan)).fillna(0)
    hex_records = [
        {
            'x': float(row.x),
            'y': float(row.y),
            'attempted': int(row.attempted),
            'made': int(row.made),
            'pct': float(ratio(row.made, row.attempted)),
            'zone': row.zone,
            'vs_league': round(float(ratio(row.made, row.attempted)) - float(league_zone_pct[row.zone]), 4),
        }
        for row in hexes.itertuples(index=False)
    ]

    return {
        'side': side,
        'attempted': int(len(rows)),
        'made': int(rows['made'].sum()),
        'hex_size': HEX_SIZE,
        'zones': _split_records(_zone_split(rows, 'zone', ZONES), league['zones'], ZONE_LABELS, 'zone'),
        'shot_types': _split_records(
            _zone_split(rows, 'shot_type', SHOT_TYPES), league['types'], SHOT_TYPE_LABELS, 'shot_type',
        ),
        'hexes': hex_records,
    }
