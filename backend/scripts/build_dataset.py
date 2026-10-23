"""Build the raw data files from the Kaggle "Historical NBA Data and Player Box Scores" dataset.

Rebuilds the five players on the floor for every team from the 2025-26 play-by-play (substitutions plus box-score
starters), splits each game into possessions, and sums possession-level stats in the same shape the lineup API
expects. Writes to backend/raw_data/:

    teams.json, games.json, players.json   small lookup tables
    possessions.csv.gz                     one row per possession
    shots.csv.gz                           one row per field goal attempt, with court location and lineups

Usage:
    python scripts/build_dataset.py [path/to/kaggle/dataset/dir]

With no path the dataset is downloaded with kagglehub (pip install kagglehub).
"""

from __future__ import annotations

import csv
import gzip
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
import pyarrow.compute as pc
import pyarrow.dataset as ds

RAW_DATA_DIR = Path(__file__).resolve().parent.parent / 'raw_data'
KAGGLE_DATASET = 'eoinamoore/historical-nba-data-and-player-box-scores'

# 2025-26 season game ids: 2 = regular season, 4 = playoffs, 5 = play-in.
SEASON_GAME_ID = r'^(225|425|525)'
GAME_TYPES = {'2': 'Regular Season', '4': 'Playoffs', '5': 'Play-In'}

CLUTCH_SECONDS = 300
CLUTCH_MARGIN = 5
# Games whose rebuilt score is further than this from the final score have gaps in their play-by-play.
MAX_SCORE_GAP = 5

PBP_COLUMNS = [
    'gameId', 'period', 'clock', 'actionType', 'subType', 'descriptor', 'qualifiers', 'description',
    'personId', 'teamId', 'teamTricode', 'possession', 'orderNumber', 'scoreHome', 'scoreAway',
    'area', 'x', 'y', 'shotResult', 'assistPersonId', 'foulDrawnPersonId',
]

ZONES = {
    'Restricted Area': 'ra',
    'In The Paint (Non-RA)': 'paint',
    'Mid-Range': 'mid',
    'Left Corner 3': 'corner3',
    'Right Corner 3': 'corner3',
    'Above the Break 3': 'atb3',
    'Backcourt': 'atb3',
}
SHOT_TYPES = {'Jump Shot': 'jumper', 'Layup': 'layup', 'DUNK': 'dunk', 'Dunk': 'dunk', 'Hook': 'hook'}

# Same counting stats as the original possession model, then the stats this dataset adds.
COUNTING_STATS = (
    'fg2_made', 'fg2_attempted', 'fg3_made', 'fg3_attempted', 'fg_made', 'fg_attempted', 'ft_made', 'ft_attempted',
    'rebounds_offense', 'rebounds_defense', 'rebound_opportunities', 'assists', 'steals', 'turnovers', 'blocks',
    'offensive_fouls', 'defensive_fouls', 'shooting_fouls', 'points', 'shot_attempts', 'shot_attempt_points',
    'ft_potential_points', 'transition_take_fouls',
    'ra_made', 'ra_attempted', 'paint_made', 'paint_attempted', 'mid_made', 'mid_attempted',
    'corner3_made', 'corner3_attempted', 'atb3_made', 'atb3_attempted',
    'dunk_made', 'dunk_attempted', 'layup_made', 'layup_attempted', 'jumper_made', 'jumper_attempted',
    'hook_made', 'hook_attempted',
    'paint_points', 'fastbreak_points', 'second_chance_points', 'points_off_turnovers',
)
POSSESSION_COLUMNS = (
    'game_id', 'period', 'offensive_team_id', 'defensive_team_id', 'offensive_player_ids', 'defensive_player_ids',
    'offense_is_home', 'clutch', 'seconds', *COUNTING_STATS,
)
SHOT_COLUMNS = (
    'game_id', 'period', 'clutch', 'offensive_team_id', 'defensive_team_id', 'offensive_player_ids',
    'defensive_player_ids', 'shooter_id', 'x', 'y', 'zone', 'shot_type', 'value', 'made',
)


def clock_seconds(clock: str | None) -> float:
    match = re.match(r'PT(\d+)M([\d.]+)S', clock or '')
    return int(match[1]) * 60 + float(match[2]) if match else 0.0


def half_court(x: float, y: float) -> tuple[float, float]:
    """Map a 0-100 full-court position to feet on one half: `x` across (0-50), `y` out from the baseline."""
    if x > 50:
        x, y = 100 - x, 100 - y
    return round(y * 0.5, 2), round(x * 0.94, 2)


@dataclass
class Possession:
    game_id: str
    period: int
    offense: str
    defense: str
    offense_lineup: tuple[str, ...]
    defense_lineup: tuple[str, ...]
    offense_is_home: bool
    clutch: bool
    start: float
    end: float | None = None
    ended: bool = False
    # 'fg' or 'ft' while a missed shot is waiting on a rebound.
    awaiting_rebound: str | None = None
    last_made_fg: bool = False
    stats: Counter = field(default_factory=Counter)

    @property
    def valid(self) -> bool:
        return len(self.offense_lineup) == 5 and len(self.defense_lineup) == 5

    def row(self) -> dict:
        return {
            'game_id': self.game_id,
            'period': self.period,
            'offensive_team_id': self.offense,
            'defensive_team_id': self.defense,
            'offensive_player_ids': ';'.join(self.offense_lineup),
            'defensive_player_ids': ';'.join(self.defense_lineup),
            'offense_is_home': int(self.offense_is_home),
            'clutch': int(self.clutch),
            'seconds': round(max(0.0, self.start - (self.end or 0.0)), 1),
            **{stat: self.stats[stat] for stat in COUNTING_STATS},
        }


class GameParser:
    """Walks one game's play-by-play in order, tracking lineups and building possessions."""

    def __init__(self, game: dict, events: pd.DataFrame, player_team: dict[str, str], starters: dict[str, set]):
        self.game = game
        self.events = events
        self.player_team = player_team
        self.starters = starters
        self.home = game['home_team_id']
        self.teams = (game['home_team_id'], game['away_team_id'])
        self.tricodes: dict[str, str] = {}
        self.possessions: list[Possession] = []
        self.shots: list[dict] = []
        self.lineups: dict[str, set] = {}
        self.current: Possession | None = None
        self.pending_defensive_fouls: list[dict] = []
        self.margin = 0
        self.bad_periods = 0
        self.technical_points = 0

    def other(self, team: str) -> str:
        return self.teams[1] if team == self.teams[0] else self.teams[0]

    def team_of(self, event) -> str | None:
        if event.personId and event.personId != '0' and event.personId in self.player_team:
            return self.player_team[event.personId]
        if event.teamId in self.teams:
            return event.teamId
        if event.teamTricode and event.teamTricode in self.tricodes:
            return self.tricodes[event.teamTricode]
        return None

    def period_starters(self, period: int, events: pd.DataFrame, previous: dict[str, set]) -> dict[str, set]:
        if period == 1:
            return {team: set(self.starters.get(team, ())) for team in self.teams}
        first_seen: dict[str, str] = {}
        for event in events.itertuples(index=False):
            involved = [(event.personId, event.actionType == 'substitution' and event.subType == 'in')]
            if event.assistPersonId:
                involved.append((event.assistPersonId, False))
            if event.foulDrawnPersonId:
                involved.append((event.foulDrawnPersonId, False))
            for person, entered in involved:
                if person and person != '0' and person in self.player_team and person not in first_seen:
                    first_seen[person] = 'in' if entered else 'on'
        lineups = {}
        for team in self.teams:
            on = {p for p, how in first_seen.items() if how == 'on' and self.player_team[p] == team}
            # Players who sat through the whole period with no event: carry them over from the last period.
            if len(on) < 5:
                carry = [p for p in previous.get(team, ()) if p not in first_seen]
                on |= set(carry[: 5 - len(on)])
            lineups[team] = on
        return lineups

    def open(self, offense: str, clock: float) -> Possession:
        previous = self.current
        start = clock
        if previous is not None:
            if previous.end is None:
                previous.end = clock
            start = previous.end
        defense = self.other(offense)
        margin = self.margin if offense == self.home else -self.margin
        possession = Possession(
            game_id=self.game['game_id'],
            period=self.period,
            offense=offense,
            defense=defense,
            offense_lineup=tuple(sorted(self.lineups.get(offense, ()))),
            defense_lineup=tuple(sorted(self.lineups.get(defense, ()))),
            offense_is_home=offense == self.home,
            clutch=self.period >= 4 and start <= CLUTCH_SECONDS and abs(margin) <= CLUTCH_MARGIN,
            start=start,
        )
        for foul in self.pending_defensive_fouls:
            if foul['offense'] == offense:
                possession.stats.update(foul['stats'])
        self.pending_defensive_fouls = []
        self.possessions.append(possession)
        self.current = possession
        return possession

    def end_current(self, clock: float) -> None:
        if self.current is not None and not self.current.ended:
            self.current.ended = True
            self.current.end = clock

    def on_offense(self, team: str, clock: float) -> Possession:
        """The possession `team` is attacking in, opening one if the ball has changed hands."""
        current = self.current
        if current is None or current.offense != team or (current.ended and not current.last_made_fg):
            return self.open(team, clock)
        return current

    def parse(self) -> None:
        for event in self.events.itertuples(index=False):
            if event.teamTricode and event.teamId in self.teams:
                self.tricodes[event.teamTricode] = event.teamId

        previous: dict[str, set] = {}
        for period, events in self.events.groupby('period', sort=True):
            self.period = int(period)
            self.lineups = self.period_starters(self.period, events, previous)
            if any(len(players) != 5 for players in self.lineups.values()):
                self.bad_periods += 1
            self.current = None
            self.pending_defensive_fouls = []
            for event in events.itertuples(index=False):
                self.handle(event)
            if self.current is not None and self.current.end is None:
                self.current.end = 0.0
            previous = {team: set(players) for team, players in self.lineups.items()}

    def handle(self, event) -> None:
        kind = event.actionType
        clock = clock_seconds(event.clock)
        team = self.team_of(event)
        qualifiers = set(event.qualifiers) if event.qualifiers is not None else set()

        if kind == 'substitution':
            if team in self.lineups:
                if event.subType == 'out':
                    self.lineups[team].discard(event.personId)
                elif event.subType == 'in':
                    self.lineups[team].add(event.personId)
            return
        if kind == 'period' and event.subType == 'end':
            if self.current is not None and self.current.end is None:
                self.current.end = 0.0
            return
        if team is None:
            return

        if kind == 'jumpball':
            if self.current is None or self.current.offense != team or self.current.ended:
                self.open(team, clock)
        elif kind in ('2pt', '3pt'):
            self.shot(event, team, clock, qualifiers)
        elif kind == 'freethrow':
            self.free_throw(event, team, clock, qualifiers)
        elif kind == 'rebound':
            self.rebound(event, clock)
        elif kind == 'turnover':
            possession = self.on_offense(team, clock)
            possession.last_made_fg = False
            possession.stats['turnovers'] += 1
            possession.awaiting_rebound = None
            self.end_current(clock)
        elif kind == 'steal':
            if self.current is not None and self.current.offense != team:
                self.current.stats['steals'] += 1
        elif kind == 'block':
            if self.current is not None and self.current.offense != team:
                self.current.stats['blocks'] += 1
        elif kind == 'foul':
            self.foul(event, team)

        self.margin = int(event.scoreHome or 0) - int(event.scoreAway or 0)

    def shot(self, event, team: str, clock: float, qualifiers: set) -> None:
        possession = self.on_offense(team, clock)
        possession.last_made_fg = False
        stats = possession.stats
        value = 3 if event.actionType == '3pt' else 2
        made = event.shotResult == 'Made'
        zone = ZONES.get(event.area, 'mid' if value == 2 else 'atb3')
        shot_type = SHOT_TYPES.get(event.subType, 'jumper')

        stats['fg_attempted'] += 1
        stats[f'fg{value}_attempted'] += 1
        stats['shot_attempts'] += 1
        stats[f'{zone}_attempted'] += 1
        stats[f'{shot_type}_attempted'] += 1
        if made:
            stats['fg_made'] += 1
            stats[f'fg{value}_made'] += 1
            stats[f'{zone}_made'] += 1
            stats[f'{shot_type}_made'] += 1
            stats['points'] += value
            stats['shot_attempt_points'] += value
            if event.assistPersonId and event.assistPersonId != '0':
                stats['assists'] += 1
            self.context_points(stats, value, qualifiers)
            possession.awaiting_rebound = None
            possession.last_made_fg = True
            self.end_current(clock)
        else:
            possession.awaiting_rebound = 'fg'

        if event.x == event.x and event.y == event.y and event.x is not None:
            across, depth = half_court(event.x, event.y)
            self.shots.append({
                'game_id': self.game['game_id'],
                'period': self.period,
                'clutch': int(possession.clutch),
                'offensive_team_id': possession.offense,
                'defensive_team_id': possession.defense,
                'offensive_player_ids': ';'.join(possession.offense_lineup),
                'defensive_player_ids': ';'.join(possession.defense_lineup),
                'shooter_id': event.personId,
                'x': across,
                'y': depth,
                'zone': {'Left Corner 3': 'lc3', 'Right Corner 3': 'rc3'}.get(event.area, zone),
                'shot_type': shot_type,
                'value': value,
                'made': int(made),
            })

    @staticmethod
    def context_points(stats: Counter, points: int, qualifiers: set) -> None:
        if 'pointsinthepaint' in qualifiers:
            stats['paint_points'] += points
        if 'fastbreak' in qualifiers:
            stats['fastbreak_points'] += points
        if '2ndchance' in qualifiers:
            stats['second_chance_points'] += points
        if 'fromturnover' in qualifiers:
            stats['points_off_turnovers'] += points

    def free_throw(self, event, team: str, clock: float, qualifiers: set) -> None:
        description = (event.description or '').lower()
        if 'technical' in description:
            # Technical free throws don't belong to either side's possession.
            self.technical_points += 'miss' not in description
            return
        match = re.match(r'(\d) of (\d)', event.subType or '')
        number, total = (int(match[1]), int(match[2])) if match else (1, 1)
        and_one = self.current is not None and self.current.offense == team and self.current.last_made_fg
        possession = self.current if and_one else self.on_offense(team, clock)
        stats = possession.stats
        made = 'miss' not in description

        stats['ft_attempted'] += 1
        # Approximation: each free throw attempt is one potential point.
        stats['ft_potential_points'] += 1
        if number == 1 and not and_one:
            stats['shot_attempts'] += 1  # A trip to the line counts as one shot attempt.
        if made:
            stats['ft_made'] += 1
            stats['points'] += 1
            if and_one:
                # Approximation: the and-one free throw is credited to the shot attempt that drew it.
                stats['shot_attempt_points'] += 1
            self.context_points(stats, 1, qualifiers - {'pointsinthepaint'})

        if number == total:
            possession.last_made_fg = False
            if made:
                possession.awaiting_rebound = None
                self.end_current(clock)
            else:
                possession.awaiting_rebound = 'ft'
        else:
            possession.awaiting_rebound = None

    def rebound(self, event, clock: float) -> None:
        possession = self.current
        if possession is None or possession.awaiting_rebound is None:
            return
        team = self.team_of(event)
        if team is None and event.possession in self.teams:
            team = event.possession
        if team is None:
            return
        possession.awaiting_rebound = None
        possession.stats['rebound_opportunities'] += 1
        if team == possession.offense:
            possession.stats['rebounds_offense'] += 1
        else:
            possession.stats['rebounds_defense'] += 1
            self.end_current(clock)

    def foul(self, event, team: str) -> None:
        if event.subType == 'technical' or (event.descriptor or '').startswith('flagrant-type-2'):
            return
        stats = Counter()
        if team == (self.current.offense if self.current else None) and not (
            self.current.ended and event.subType != 'offensive'
        ):
            stats['offensive_fouls'] += 1
            if self.current is not None:
                self.current.stats.update(stats)
            return
        stats['defensive_fouls'] += 1
        if event.descriptor == 'shooting':
            stats['shooting_fouls'] += 1
        if event.descriptor == 'transition take':
            stats['transition_take_fouls'] += 1
        offense = self.other(team)
        if self.current is not None and self.current.offense == offense and (
            not self.current.ended or self.current.last_made_fg
        ):
            self.current.stats.update(stats)
        else:
            # The fouled team's possession hasn't started yet (e.g. a foul right after a rebound).
            self.pending_defensive_fouls.append({'offense': offense, 'stats': stats})


def load_kaggle_dir(argv: list[str]) -> Path:
    if len(argv) > 1:
        return Path(argv[1])
    import kagglehub

    return Path(kagglehub.dataset_download(KAGGLE_DATASET))


def build_games(source: Path) -> pd.DataFrame:
    games = pd.read_csv(source / 'Games.csv', low_memory=False, dtype={'gameId': str})
    games = games[games.gameId.str.match(SEASON_GAME_ID)].copy()
    return pd.DataFrame({
        'game_id': games.gameId,
        'date': games.gameDateTimeEst.str[:10],
        'game_type': games.gameId.str[0].map(GAME_TYPES),
        'home_team_id': games.hometeamId.astype('int64').astype(str),
        'away_team_id': games.awayteamId.astype('int64').astype(str),
        'home_score': games.homeScore.astype(int),
        'away_score': games.awayScore.astype(int),
    }).sort_values(['date', 'game_id'])


def build_teams(source: Path, pbp: pd.DataFrame) -> list[dict]:
    raw = pd.read_csv(source / 'Games.csv', low_memory=False, dtype={'gameId': str})
    raw = raw[raw.gameId.str.match(SEASON_GAME_ID)]
    # The play-by-play's tricodes are the current abbreviations (TeamHistories has some stale ones, e.g. SAN).
    tagged = pbp[pbp.teamId.notna() & pbp.teamTricode.notna()]
    abbrev = tagged.groupby(tagged.teamId.astype('int64')).teamTricode.agg(lambda codes: codes.mode()[0]).to_dict()
    teams = {}
    for prefix in ('hometeam', 'awayteam'):
        for row in raw[[f'{prefix}Id', f'{prefix}City', f'{prefix}Name']].drop_duplicates().itertuples(index=False):
            team_id = int(row[0])
            teams[str(team_id)] = {
                'team_id': str(team_id),
                'city': row[1],
                'name': f'{row[1]} {row[2]}',
                'nickname': row[2],
                'abbreviation': abbrev.get(team_id, row[2][:3].upper()),
            }
    return sorted(teams.values(), key=lambda team: team['name'])


def build_box_scores(source: Path) -> pd.DataFrame:
    columns = [
        'personId', 'firstName', 'lastName', 'gameId', 'playerteamId', 'startingPosition', 'numMinutes', 'points',
        'reboundsTotal', 'assists', 'steals', 'blocks', 'gameDateTimeEst',
    ]
    box = pd.read_csv(source / 'PlayerStatistics.csv', usecols=columns, low_memory=False, dtype={'gameId': str})
    box = box[box.gameId.str.match(SEASON_GAME_ID) & box.personId.notna() & box.playerteamId.notna()].copy()
    box['personId'] = box.personId.astype('int64').astype(str)
    box['numMinutes'] = pd.to_numeric(box.numMinutes, errors='coerce')
    box['playerteamId'] = box.playerteamId.astype('int64').astype(str)
    return box


def build_players(source: Path, box: pd.DataFrame) -> list[dict]:
    bio = pd.read_csv(source / 'Players.csv', low_memory=False)
    bio['personId'] = bio.personId.astype('int64').astype(str)
    bio = bio.set_index('personId')

    played = box[box.numMinutes.fillna(0) > 0]
    regular = played[played.gameId.str.startswith('2')]
    averages = regular.groupby('personId').agg(
        games=('gameId', 'nunique'), minutes=('numMinutes', 'mean'), points=('points', 'mean'),
        rebounds=('reboundsTotal', 'mean'), assists=('assists', 'mean'), steals=('steals', 'mean'),
        blocks=('blocks', 'mean'),
    )
    latest_team = box.sort_values('gameDateTimeEst').groupby('personId').playerteamId.last()
    names = box.groupby('personId')[['firstName', 'lastName']].last()

    def clean(value):
        return None if pd.isna(value) else value

    players = []
    for person_id, team_id in latest_team.items():
        info = bio.loc[person_id] if person_id in bio.index else None
        positions = [] if info is None else [
            label for label, flag in (('G', 'guard'), ('F', 'forward'), ('C', 'center')) if info[flag] is True or info[flag] == 1
        ]
        avg = averages.loc[person_id] if person_id in averages.index else None
        players.append({
            'player_id': person_id,
            'name': f'{names.loc[person_id].firstName} {names.loc[person_id].lastName}'.strip(),
            'team_id': team_id,
            'position': '-'.join(positions),
            'height_in': None if info is None else clean(info.heightInches),
            'weight_lb': None if info is None else clean(info.bodyWeightLbs),
            'birth_date': None if info is None else clean(info.birthDate),
            'country': None if info is None else clean(info.country),
            'school': None if info is None else clean(info.school),
            'draft_year': None if info is None else clean(info.draftYear),
            'draft_round': None if info is None else clean(info.draftRound),
            'draft_number': None if info is None else clean(info.draftNumber),
            'games': 0 if avg is None else int(avg.games),
            'minutes_per_game': 0 if avg is None else round(float(avg.minutes), 1),
            'points_per_game': 0 if avg is None else round(float(avg.points), 1),
            'rebounds_per_game': 0 if avg is None else round(float(avg.rebounds), 1),
            'assists_per_game': 0 if avg is None else round(float(avg.assists), 1),
            'steals_per_game': 0 if avg is None else round(float(avg.steals), 1),
            'blocks_per_game': 0 if avg is None else round(float(avg.blocks), 1),
        })
    for player in players:
        for key in ('height_in', 'weight_lb', 'draft_year', 'draft_round', 'draft_number'):
            value = player[key]
            if value is not None:
                try:
                    player[key] = int(float(value))
                except ValueError:
                    player[key] = None
    return players


def write_csv(path: Path, columns: tuple[str, ...], rows: list[dict]) -> None:
    with gzip.open(path, 'wt', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def main(argv: list[str]) -> None:
    source = load_kaggle_dir(argv)
    RAW_DATA_DIR.mkdir(exist_ok=True)
    print(f'Reading {source}')

    games = build_games(source)
    box = build_box_scores(source)
    players = build_players(source, box)

    player_team = {(row.gameId, row.personId): row.playerteamId for row in box.itertuples(index=False)}
    starters: dict[str, dict[str, set]] = defaultdict(lambda: defaultdict(set))
    for row in box[box.startingPosition.notna()].itertuples(index=False):
        starters[row.gameId][row.playerteamId].add(row.personId)

    pbp = ds.dataset(source / 'PlayByPlay.parquet').to_table(
        columns=PBP_COLUMNS, filter=pc.match_substring_regex(ds.field('gameId'), SEASON_GAME_ID),
    ).to_pandas()
    pbp = pbp[pbp.actionType.str.islower()].sort_values(['gameId', 'period', 'orderNumber'])
    print(f'{len(pbp):,} play-by-play events across {pbp.gameId.nunique()} games')
    teams = build_teams(source, pbp)

    possessions: list[dict] = []
    shots: list[dict] = []
    totals = Counter()
    score_gaps = []
    game_rows = games.set_index('game_id').to_dict('index')
    for game_id, events in pbp.groupby('gameId', sort=False):
        if game_id not in game_rows:
            continue
        game = {'game_id': game_id, **game_rows[game_id]}
        parser = GameParser(game, events, _players_for(player_team, game_id), starters.get(game_id, {}))
        parser.parse()
        rebuilt = sum(p.stats['points'] for p in parser.possessions) + parser.technical_points
        gap = abs(rebuilt - game['home_score'] - game['away_score'])
        score_gaps.append(gap)
        if gap > MAX_SCORE_GAP:
            totals['dropped_games'] += 1
            continue
        valid = [p for p in parser.possessions if p.valid]
        totals['possessions'] += len(parser.possessions)
        totals['valid'] += len(valid)
        totals['bad_periods'] += parser.bad_periods
        totals['periods'] += events.period.nunique() * 2
        possessions.extend(p.row() for p in valid)
        shots.extend(shot for shot in parser.shots if shot['offensive_player_ids'].count(';') == 4
                     and shot['defensive_player_ids'].count(';') == 4)

    print(f"{totals['possessions']:,} possessions built, {totals['valid']:,} with both lineups known "
          f"({totals['valid'] / totals['possessions']:.1%})")
    print(f"Period lineups that needed repair or were dropped: {totals['bad_periods']} of {totals['periods']}")
    gaps = pd.Series(score_gaps)
    print(f'Score check: exact in {(gaps == 0).mean():.1%} of games; '
          f"dropped {totals['dropped_games']} games more than {MAX_SCORE_GAP} points off")

    played = {pid for row in possessions for pid in row['offensive_player_ids'].split(';')}
    players = [player for player in players if player['player_id'] in played]

    (RAW_DATA_DIR / 'teams.json').write_text(json.dumps(teams, indent=1))
    (RAW_DATA_DIR / 'games.json').write_text(json.dumps(games.to_dict('records'), indent=1))
    (RAW_DATA_DIR / 'players.json').write_text(json.dumps(players, indent=1))
    write_csv(RAW_DATA_DIR / 'possessions.csv.gz', POSSESSION_COLUMNS, possessions)
    write_csv(RAW_DATA_DIR / 'shots.csv.gz', SHOT_COLUMNS, shots)
    print(f'Wrote {len(teams)} teams, {len(games)} games, {len(players)} players, '
          f'{len(possessions):,} possessions, {len(shots):,} shots to {RAW_DATA_DIR}')


_PLAYERS_BY_GAME: dict[str, dict[str, str]] = {}


def _players_for(player_team: dict[tuple[str, str], str], game_id: str) -> dict[str, str]:
    if not _PLAYERS_BY_GAME:
        for (gid, person), team in player_team.items():
            _PLAYERS_BY_GAME.setdefault(gid, {})[person] = team
    return _PLAYERS_BY_GAME.get(game_id, {})


if __name__ == '__main__':
    main(sys.argv)
