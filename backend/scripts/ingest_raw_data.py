# Loads the teams, games and players written by scripts/build_dataset.py into the database. Possessions and
# shots stay in raw_data/*.csv.gz and are read straight into memory by app.helpers.data.

import json
import os
from pathlib import Path

import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'app.settings')

django.setup()

from django.db import transaction
from app.dbmodels.models import Game, Team, Player

RAW_DATA_DIR = Path(__file__).resolve().parent.parent / 'raw_data'
PLAYER_FIELDS = (
    'name', 'position', 'height_in', 'weight_lb', 'birth_date', 'country', 'school', 'draft_year', 'draft_round',
    'draft_number', 'games', 'minutes_per_game', 'points_per_game', 'rebounds_per_game', 'assists_per_game',
    'steals_per_game', 'blocks_per_game',
)


def load_json(filename):
    with open(RAW_DATA_DIR / filename) as raw_file:
        return json.load(raw_file)


def delete_all():
    for model in (Player, Game, Team):
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


if __name__ == '__main__':
    with transaction.atomic():
        delete_all()
        ingest_teams()
        ingest_games()
        ingest_players()
    print(f'Loaded {Team.objects.count()} teams, {Game.objects.count()} games and {Player.objects.count()} players')
