# Loads the files written by scripts/build_dataset.py into the database.

import csv
import gzip
import json
import os
from pathlib import Path

import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'app.settings')

django.setup()

from django.db import transaction
from app.dbmodels.models import Game, Team, Player, Possession, Shot

RAW_DATA_DIR = Path(__file__).resolve().parent.parent / 'raw_data'
BATCH_SIZE = 5000

POSSESSION_COUNTING_FIELDS = (
    'period', 'fg2_made', 'fg2_attempted', 'fg3_made', 'fg3_attempted', 'fg_made', 'fg_attempted', 'ft_made',
    'ft_attempted', 'rebounds_offense', 'rebounds_defense', 'rebound_opportunities', 'assists', 'steals',
    'turnovers', 'blocks', 'offensive_fouls', 'defensive_fouls', 'shooting_fouls', 'points', 'shot_attempts',
    'shot_attempt_points', 'ft_potential_points', 'transition_take_fouls',
    'ra_made', 'ra_attempted', 'paint_made', 'paint_attempted', 'mid_made', 'mid_attempted',
    'corner3_made', 'corner3_attempted', 'atb3_made', 'atb3_attempted',
    'dunk_made', 'dunk_attempted', 'layup_made', 'layup_attempted', 'jumper_made', 'jumper_attempted',
    'hook_made', 'hook_attempted',
    'paint_points', 'fastbreak_points', 'second_chance_points', 'points_off_turnovers',
)

PLAYER_FIELDS = (
    'name', 'position', 'height_in', 'weight_lb', 'birth_date', 'country', 'school', 'draft_year', 'draft_round',
    'draft_number', 'games', 'minutes_per_game', 'points_per_game', 'rebounds_per_game', 'assists_per_game',
    'steals_per_game', 'blocks_per_game',
)


def load_json(filename):
    with open(RAW_DATA_DIR / filename) as raw_file:
        return json.load(raw_file)


def load_csv(filename):
    with gzip.open(RAW_DATA_DIR / filename, 'rt', newline='') as raw_file:
        yield from csv.DictReader(raw_file)


def player_ids(raw_value):
    return [int(player_id) for player_id in raw_value.split(';')]


def bulk_create(model, rows):
    batch = []
    for row in rows:
        batch.append(row)
        if len(batch) == BATCH_SIZE:
            model.objects.bulk_create(batch)
            batch = []
    model.objects.bulk_create(batch)


def delete_all():
    for model in (Shot, Possession, Player, Game, Team):
        model.objects.all().delete()


def ingest_teams():
    Team.objects.bulk_create([
        Team(id=team['team_id'], name=team['name'], city=team['city'], nickname=team['nickname'],
             abbreviation=team['abbreviation'])
        for team in load_json('teams.json')
    ])


def ingest_games():
    Game.objects.bulk_create([
        Game(id=game['game_id'], date=game['date'], game_type=game['game_type'], home_team_id=game['home_team_id'],
             away_team_id=game['away_team_id'], home_score=game['home_score'], away_score=game['away_score'])
        for game in load_json('games.json')
    ])


def ingest_players():
    Player.objects.bulk_create([
        Player(id=player['player_id'], team_id=player['team_id'], **{field: player[field] for field in PLAYER_FIELDS})
        for player in load_json('players.json')
    ])


def ingest_possessions():
    bulk_create(Possession, (
        Possession(
            game_id=row['game_id'],
            offensive_team_id=row['offensive_team_id'],
            defensive_team_id=row['defensive_team_id'],
            offensive_player_ids=player_ids(row['offensive_player_ids']),
            defensive_player_ids=player_ids(row['defensive_player_ids']),
            seconds=float(row['seconds']),
            offense_is_home=row['offense_is_home'] == '1',
            clutch=row['clutch'] == '1',
            **{field: int(row[field]) for field in POSSESSION_COUNTING_FIELDS},
        )
        for row in load_csv('possessions.csv.gz')
    ))


def ingest_shots():
    bulk_create(Shot, (
        Shot(
            game_id=row['game_id'],
            period=int(row['period']),
            clutch=row['clutch'] == '1',
            offensive_team_id=row['offensive_team_id'],
            defensive_team_id=row['defensive_team_id'],
            offensive_player_ids=player_ids(row['offensive_player_ids']),
            defensive_player_ids=player_ids(row['defensive_player_ids']),
            shooter_id=int(row['shooter_id']),
            x=float(row['x']),
            y=float(row['y']),
            zone=row['zone'],
            shot_type=row['shot_type'],
            value=int(row['value']),
            made=row['made'] == '1',
        )
        for row in load_csv('shots.csv.gz')
    ))


if __name__ == '__main__':
    with transaction.atomic():
        delete_all()
        ingest_teams()
        ingest_games()
        ingest_players()
        ingest_possessions()
        ingest_shots()
    print(f'Loaded {Possession.objects.count():,} possessions and {Shot.objects.count():,} shots')
