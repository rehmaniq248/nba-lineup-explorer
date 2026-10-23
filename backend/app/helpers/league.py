"""League-wide averages and dataset metadata."""

from __future__ import annotations

from typing import Any

from app.dbmodels.models import Game, Player, Possession, Shot
from app.helpers.data import APPROXIMATIONS, CONTEXT_POINTS, SHOT_TYPES, SHOT_ZONES, Filters, game_mask, possessions
from app.helpers.lineups import ratio


def get_league_averages(filters: Filters) -> dict[str, Any]:
    """Per-possession league rates over the same games a filtered view covers (each possession counted once)."""
    frame = possessions()
    totals = frame[game_mask(frame, filters)].sum(numeric_only=True)
    poss = totals['possessions']
    averages = {
        'possessions': int(poss),
        'offensive_rating': float(ratio(100 * totals['points'], poss, 2)),
        'fg2': float(ratio(totals['fg2_made'], totals['fg2_attempted'])),
        'fg3': float(ratio(totals['fg3_made'], totals['fg3_attempted'])),
        'ft': float(ratio(totals['ft_made'], totals['ft_attempted'])),
        'efg': float(ratio(totals['fg_made'] + 0.5 * totals['fg3_made'], totals['fg_attempted'])),
        'oreb': float(ratio(totals['rebounds_offense'], totals['rebound_opportunities'])),
        'dreb': float(ratio(totals['rebounds_defense'], totals['rebound_opportunities'])),
        'turnover': float(ratio(totals['turnovers'], poss)),
        'ft_rate': float(ratio(totals['ft_attempted'], totals['fg_attempted'])),
        'fg3_rate': float(ratio(totals['fg3_attempted'], totals['fg_attempted'])),
        # Possessions per team per 48 minutes: both teams' possessions share the game clock.
        'pace': float(ratio(48 * 60 * poss / 2, totals['seconds'], 1)),
    }
    for zone in (*SHOT_ZONES, *SHOT_TYPES):
        averages[zone] = float(ratio(totals[f'{zone}_made'], totals[f'{zone}_attempted']))
        averages[f'{zone}_share'] = float(ratio(totals[f'{zone}_attempted'], totals['fg_attempted']))
    for context in CONTEXT_POINTS:
        averages[f'{context}_per100'] = float(ratio(100 * totals[context], poss, 2))
    return averages


def get_meta() -> dict[str, Any]:
    games = Game.objects.order_by('date')
    first, last = games.first(), games.last()
    return {
        'season': '2025-26',
        'source': 'Kaggle: eoinamoore/historical-nba-data-and-player-box-scores',
        'first_game': first.date.isoformat() if first else None,
        'last_game': last.date.isoformat() if last else None,
        'games': {game_type: games.filter(game_type=game_type).count()
                  for game_type in ('Regular Season', 'Play-In', 'Playoffs')},
        'possessions': Possession.objects.count(),
        'shots': Shot.objects.count(),
        'players': Player.objects.count(),
        'approximations': APPROXIMATIONS,
        'notes': [
            'Lineups are rebuilt from play-by-play substitutions and box-score starters. About 0.1% of '
            'possessions had a lineup that could not be rebuilt and are left out.',
            'Technical free throws are not credited to either lineup.',
            'Clutch: last five minutes of the fourth quarter or overtime with the score within five.',
            'End-of-quarter heaves are not field goal attempts (NBA rule from 2025-26) and are left out.',
        ],
    }
