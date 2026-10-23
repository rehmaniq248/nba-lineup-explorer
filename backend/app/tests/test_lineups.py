import datetime

from django.test import TestCase

from app.dbmodels.models import Game, Player, Possession, Shot, Team
from app.helpers.data import clear_cache
from app.helpers.lineups import get_lineup_league_summary_stats
from app.helpers.players import get_player_on_off_stats
from app.helpers.shots import get_shot_chart

STAT_DEFAULTS = {
    'period': 1, 'seconds': 10.0, 'offense_is_home': True, 'clutch': False, 'fg2_made': 0, 'fg2_attempted': 0,
    'fg3_made': 0, 'fg3_attempted': 0, 'fg_made': 0, 'fg_attempted': 0, 'ft_made': 0, 'ft_attempted': 0,
    'rebounds_offense': 0, 'rebounds_defense': 0, 'rebound_opportunities': 0, 'assists': 0, 'steals': 0,
    'turnovers': 0, 'blocks': 0, 'offensive_fouls': 0, 'defensive_fouls': 0, 'shooting_fouls': 0, 'points': 0,
    'shot_attempts': 0, 'shot_attempt_points': 0, 'ft_potential_points': 0, 'transition_take_fouls': 0,
    'ra_made': 0, 'ra_attempted': 0, 'paint_made': 0, 'paint_attempted': 0, 'mid_made': 0, 'mid_attempted': 0,
    'corner3_made': 0, 'corner3_attempted': 0, 'atb3_made': 0, 'atb3_attempted': 0, 'dunk_made': 0,
    'dunk_attempted': 0, 'layup_made': 0, 'layup_attempted': 0, 'jumper_made': 0, 'jumper_attempted': 0,
    'hook_made': 0, 'hook_attempted': 0, 'paint_points': 0, 'fastbreak_points': 0, 'second_chance_points': 0,
    'points_off_turnovers': 0,
}


class LineupSummaryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.team_a = Team.objects.create(id=1, name='A Team', city='A', nickname='Team', abbreviation='AAA')
        cls.team_b = Team.objects.create(id=2, name='B Team', city='B', nickname='Team', abbreviation='BBB')
        cls.game = Game.objects.create(
            id=100, date=datetime.date(2025, 11, 1), game_type='Regular Season', home_team=cls.team_a,
            away_team=cls.team_b, home_score=2, away_score=3,
        )
        cls.a = [Player.objects.create(id=10 + i, team=cls.team_a, name=f'A{i}', position='G' if i < 2 else 'C',
                                       height_in=75 + i) for i in range(5)]
        cls.b = [Player.objects.create(id=20 + i, team=cls.team_b, name=f'B{i}', position='F') for i in range(5)]
        # A sixth A player who only plays the third possession, so the A starters have an "off" split.
        cls.a_sub = Player.objects.create(id=15, team=cls.team_a, name='A Sub', position='F')
        cls.add_possession(cls.team_a, cls.team_b, cls.a, points=2, fg2_made=1, fg2_attempted=1, fg_made=1,
                           fg_attempted=1, ra_made=1, ra_attempted=1, paint_points=2)
        cls.add_possession(cls.team_a, cls.team_b, cls.a, points=0, fg2_attempted=1, fg_attempted=1,
                           rebound_opportunities=1, rebounds_offense=1, mid_attempted=1)
        cls.add_possession(cls.team_b, cls.team_a, [*cls.a[:4], cls.a_sub], points=3, fg3_made=1, fg3_attempted=1,
                           fg_made=1, fg_attempted=1, offense_is_home=False, clutch=True)
        Shot.objects.create(
            game=cls.game, period=1, clutch=False, offensive_team=cls.team_a, defensive_team=cls.team_b,
            offensive_player_ids=[p.id for p in cls.a], defensive_player_ids=[p.id for p in cls.b],
            shooter_id=cls.a[0].id, x=25, y=6, zone='ra', shot_type='layup', value=2, made=True,
        )

    @classmethod
    def add_possession(cls, offense, defense, a_players, **stats):
        players = {cls.team_a: a_players, cls.team_b: cls.b}
        Possession.objects.create(
            game=cls.game, offensive_team=offense, defensive_team=defense,
            offensive_player_ids=[p.id for p in players[offense]],
            defensive_player_ids=[p.id for p in players[defense]],
            **{**STAT_DEFAULTS, **stats},
        )

    def setUp(self):
        clear_cache()

    def lineup_for(self, team_players, **kwargs):
        rows, _ = get_lineup_league_summary_stats(lineup_size=5, **kwargs)
        ids = sorted(str(p.id) for p in team_players)
        return next(row for row in rows if row['player_ids'] == ids)

    def test_five_man_split_between_offense_and_defense(self):
        row = self.lineup_for(self.b)
        self.assertEqual(row['offensive_possessions'], 1)
        self.assertEqual(row['offensive_points'], 3)
        self.assertEqual(row['defensive_possessions'], 2)
        self.assertEqual(row['defensive_points'], 2)
        self.assertEqual(row['total_possessions'], 3)
        self.assertEqual(row['defensive_fg_pct'], 0.5)
        self.assertEqual(row['offensive_fg3_pct'], 1)
        self.assertEqual(row['team_id'], str(self.team_b.id))
        self.assertEqual(row['games_played'], 1)

    def test_ratings(self):
        row = self.lineup_for(self.b)
        self.assertEqual(row['offensive_rating'], 300)
        self.assertEqual(row['defensive_rating'], 100)
        self.assertEqual(row['net_rating'], 200)
        self.assertEqual(row['defensive_efg_pct'], 0.5)
        self.assertEqual(row['offensive_efg_pct'], 1.5)
        self.assertEqual(row['opponent_oreb_pct'], 1)
        self.assertEqual(row['minutes'], 0.5)
        self.assertEqual(row['defensive_ra_pct'], 1)
        self.assertEqual(row['defensive_paint_points_per100'], 100)

    def test_lineup_profile(self):
        row = self.lineup_for(self.a)
        self.assertEqual((row['guards'], row['centers']), (2, 3))
        self.assertEqual(row['avg_height_in'], 77)
        self.assertEqual(row['players'][0]['position'], 'G')

    def test_lineup_size_generates_combinations(self):
        rows, total = get_lineup_league_summary_stats(lineup_size=2, team_id=str(self.team_b.id))
        self.assertEqual(total, 10)  # C(5,2)
        self.assertTrue(all(row['total_possessions'] == 3 for row in rows))
        one_man, _ = get_lineup_league_summary_stats(lineup_size=1)
        self.assertEqual(sum(row['offensive_possessions'] for row in one_man), 3 * 5)

    def test_filters_and_sorting(self):
        rows, total = get_lineup_league_summary_stats(team_id=str(self.team_b.id))
        self.assertEqual((len(rows), rows[0]['team_name']), (1, 'B Team'))
        rows, _ = get_lineup_league_summary_stats(lineup_size=1, player_ids=[str(self.a[0].id)])
        self.assertEqual(len(rows), 1)
        rows, _ = get_lineup_league_summary_stats(lineup_size=1, exclude_player_ids=[str(p.id) for p in self.b])
        self.assertEqual({row['team_name'] for row in rows}, {'A Team'})
        rows, _ = get_lineup_league_summary_stats(sort_by='net_rating', order='asc')
        self.assertEqual(rows[0]['team_name'], 'A Team')
        rows, total = get_lineup_league_summary_stats(lineup_size=1, limit=3, offset=2)
        self.assertEqual((len(rows), total), (3, 11))
        _, total = get_lineup_league_summary_stats(min_possessions=4)
        self.assertEqual(total, 0)
        rows, _ = get_lineup_league_summary_stats(lineup_size=1, search='sub')
        self.assertEqual([row['players'][0]['name'] for row in rows], ['A Sub'])

    def test_context_filters(self):
        _, total = get_lineup_league_summary_stats(clutch=True)
        self.assertEqual(total, 2)  # Only the third possession: B's lineup and the A lineup with the sub.
        row = self.lineup_for(self.b, location='away')
        self.assertEqual((row['offensive_possessions'], row['defensive_possessions']), (1, 2))
        _, total = get_lineup_league_summary_stats(game_type='Playoffs')
        self.assertEqual(total, 0)

    def test_rejects_unknown_sort(self):
        with self.assertRaises(ValueError):
            get_lineup_league_summary_stats(sort_by='nope')

    def test_on_off(self):
        rows, _ = get_player_on_off_stats(player_ids=[str(self.a[4].id)])
        row = rows[0]
        self.assertEqual((row['possessions'], row['off_possessions']), (2, 1))
        self.assertEqual(row['on']['offensive_rating'], 100)
        self.assertEqual(row['off']['defensive_rating'], 300)
        self.assertEqual(row['height_in'], 79)

    def test_shot_chart(self):
        chart = get_shot_chart(team_id=str(self.team_a.id), player_ids=[str(self.a[0].id)])
        self.assertEqual((chart['attempted'], chart['made']), (1, 1))
        self.assertEqual(chart['zones'][0]['zone'], 'ra')
        self.assertEqual(chart['zones'][0]['pct'], 1)
        self.assertEqual(len(chart['hexes']), 1)
        self.assertEqual(get_shot_chart(team_id=str(self.team_b.id))['attempted'], 0)

    def test_endpoint_validation(self):
        self.assertEqual(self.client.get('/api/v1/lineups?sort_by=nope').status_code, 400)
        self.assertEqual(self.client.get('/api/v1/lineups?team_id=xyz').status_code, 400)
        self.assertEqual(self.client.get('/api/v1/lineups?game_type=Summer').status_code, 400)
        self.assertEqual(self.client.get('/api/v1/shots?side=nope').status_code, 400)
        self.assertEqual(self.client.get('/api/v1/lineups/trend').status_code, 400)
        response = self.client.get('/api/v1/lineups?lineup_size=1&limit=4')
        self.assertEqual((response.status_code, len(response.json()), response['X-Total-Count']), (200, 4, '11'))

    def test_other_endpoints(self):
        response = self.client.get('/api/v1/teams')
        self.assertEqual([team['name'] for team in response.json()], ['A Team', 'B Team'])
        trend = self.client.get(f'/api/v1/lineups/trend?team_id=2&player_ids={self.b[0].id}').json()
        self.assertEqual(trend[0]['month'], '2025-11')
        self.assertEqual(self.client.get('/api/v1/league').json()['possessions'], 3)
        self.assertIn('shot_attempt_points', self.client.get('/api/v1/meta').json()['approximations'])
        self.assertEqual(self.client.get('/api/v1/players?limit=2')['X-Total-Count'], '11')
