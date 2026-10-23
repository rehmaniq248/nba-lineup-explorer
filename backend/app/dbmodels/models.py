# -*- coding: utf-8 -*-
"""Contains models related to stats"""
from django.contrib.postgres.fields import ArrayField
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


class Possession(models.Model):
    class Meta:
        db_table = 'possession'

    id = models.BigAutoField(primary_key=True)
    game = models.ForeignKey(Game, on_delete=models.CASCADE, db_index=True, null=False)
    offensive_team = models.ForeignKey(
        Team, on_delete=models.PROTECT, db_index=True, null=False, related_name='offensive_possessions',
    )
    defensive_team = models.ForeignKey(
        Team, on_delete=models.PROTECT, db_index=True, null=False, related_name='defensive_possessions',
    )
    offensive_player_ids = ArrayField(models.BigIntegerField(), size=5)
    defensive_player_ids = ArrayField(models.BigIntegerField(), size=5)
    period = models.SmallIntegerField(null=False)
    seconds = models.FloatField(null=False)
    offense_is_home = models.BooleanField(null=False)
    # Last five minutes of the fourth quarter or overtime with the score within five.
    clutch = models.BooleanField(null=False)
    fg2_made = models.IntegerField(null=False)
    fg2_attempted = models.IntegerField(null=False)
    fg3_made = models.IntegerField(null=False)
    fg3_attempted = models.IntegerField(null=False)
    fg_made = models.IntegerField(null=False)
    fg_attempted = models.IntegerField(null=False)
    ft_made = models.IntegerField(null=False)
    ft_attempted = models.IntegerField(null=False)
    rebounds_offense = models.IntegerField(null=False)
    rebounds_defense = models.IntegerField(null=False)
    rebound_opportunities = models.IntegerField(null=False)
    assists = models.IntegerField(null=False)
    steals = models.IntegerField(null=False)
    turnovers = models.IntegerField(null=False)
    blocks = models.IntegerField(null=False)
    offensive_fouls = models.IntegerField(null=False)
    defensive_fouls = models.IntegerField(null=False)
    shooting_fouls = models.IntegerField(null=False)
    points = models.IntegerField(null=False)
    shot_attempts = models.IntegerField(null=False)
    # Approximation: points from made field goals plus and-one free throws.
    shot_attempt_points = models.IntegerField(null=False)
    # Approximation: one potential point per free throw attempted.
    ft_potential_points = models.IntegerField(null=False)
    transition_take_fouls = models.IntegerField(null=False)
    ra_made = models.IntegerField(null=False)
    ra_attempted = models.IntegerField(null=False)
    paint_made = models.IntegerField(null=False)
    paint_attempted = models.IntegerField(null=False)
    mid_made = models.IntegerField(null=False)
    mid_attempted = models.IntegerField(null=False)
    corner3_made = models.IntegerField(null=False)
    corner3_attempted = models.IntegerField(null=False)
    atb3_made = models.IntegerField(null=False)
    atb3_attempted = models.IntegerField(null=False)
    dunk_made = models.IntegerField(null=False)
    dunk_attempted = models.IntegerField(null=False)
    layup_made = models.IntegerField(null=False)
    layup_attempted = models.IntegerField(null=False)
    jumper_made = models.IntegerField(null=False)
    jumper_attempted = models.IntegerField(null=False)
    hook_made = models.IntegerField(null=False)
    hook_attempted = models.IntegerField(null=False)
    paint_points = models.IntegerField(null=False)
    fastbreak_points = models.IntegerField(null=False)
    second_chance_points = models.IntegerField(null=False)
    points_off_turnovers = models.IntegerField(null=False)


class Shot(models.Model):
    class Meta:
        db_table = 'shot'

    id = models.BigAutoField(primary_key=True)
    game = models.ForeignKey(Game, on_delete=models.CASCADE, db_index=True, null=False)
    period = models.SmallIntegerField(null=False)
    clutch = models.BooleanField(null=False)
    offensive_team = models.ForeignKey(Team, on_delete=models.PROTECT, null=False, related_name='shots_taken')
    defensive_team = models.ForeignKey(Team, on_delete=models.PROTECT, null=False, related_name='shots_allowed')
    offensive_player_ids = ArrayField(models.BigIntegerField(), size=5)
    defensive_player_ids = ArrayField(models.BigIntegerField(), size=5)
    shooter_id = models.BigIntegerField(null=False)
    # Feet on a half court: x across the floor (0-50), y out from the baseline (basket at about 5.25).
    x = models.FloatField(null=False)
    y = models.FloatField(null=False)
    zone = models.CharField(max_length=8, null=False)
    shot_type = models.CharField(max_length=8, null=False)
    value = models.SmallIntegerField(null=False)
    made = models.BooleanField(null=False)
