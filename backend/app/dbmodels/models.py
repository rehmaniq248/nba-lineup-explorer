# -*- coding: utf-8 -*-
"""Contains models related to stats.

Possessions and shots are not tables: they are read from backend/raw_data (see app.helpers.data).
"""
from django.db import models

GAME_TYPES = ('Regular Season', 'Play-In', 'Playoffs')


class Team(models.Model):
    class Meta:
        db_table = 'team'

    # NBA team id, e.g. 1610612747 for the Lakers.
    id = models.BigIntegerField(primary_key=True)
    name = models.TextField(null=False)
    city = models.TextField(null=False)
    nickname = models.TextField(null=False)
    abbreviation = models.CharField(max_length=4, null=False)


class Game(models.Model):
    class Meta:
        db_table = 'game'

    id = models.BigIntegerField(primary_key=True)
    date = models.DateField(null=False, db_index=True)
    game_type = models.TextField(null=False, choices=[(game_type, game_type) for game_type in GAME_TYPES])
    home_team = models.ForeignKey(Team, null=False, on_delete=models.PROTECT, related_name='home_games')
    away_team = models.ForeignKey(Team, null=False, on_delete=models.PROTECT, related_name='away_games')
    home_score = models.IntegerField(null=False)
    away_score = models.IntegerField(null=False)


class Player(models.Model):
    class Meta:
        db_table = 'player'

    id = models.BigIntegerField(primary_key=True)
    # The last team the player suited up for this season.
    team = models.ForeignKey(Team, null=False, on_delete=models.PROTECT)
    name = models.TextField(null=False)
    position = models.TextField(null=False, blank=True)
    height_in = models.IntegerField(null=True)
    weight_lb = models.IntegerField(null=True)
    birth_date = models.DateField(null=True)
    country = models.TextField(null=True)
    school = models.TextField(null=True)
    draft_year = models.IntegerField(null=True)
    draft_round = models.IntegerField(null=True)
    draft_number = models.IntegerField(null=True)
    # Regular season box-score averages.
    games = models.IntegerField(null=False, default=0)
    minutes_per_game = models.FloatField(null=False, default=0)
    points_per_game = models.FloatField(null=False, default=0)
    rebounds_per_game = models.FloatField(null=False, default=0)
    assists_per_game = models.FloatField(null=False, default=0)
    steals_per_game = models.FloatField(null=False, default=0)
    blocks_per_game = models.FloatField(null=False, default=0)
