# NBA Lineup Explorer · 2025-26

Live: https://nba-lineup-explorer.vercel.app

A lineup and player-impact dashboard for the 2025-26 NBA season. It rebuilds who was on the floor for every
possession from play-by-play data, sums each lineup's stats on both ends, and presents them for coaches and
front offices: leaderboards, matchup splits, shot charts, rebounding and size, ball security and player on/off.

Angular 21 frontend, Django 5.2 + Django REST Framework backend, PostgreSQL.

## Data

Source: [Historical NBA Data and Player Box Scores](https://www.kaggle.com/datasets/eoinamoore/historical-nba-data-and-player-box-scores)
on Kaggle (built from version 522). `backend/scripts/build_dataset.py` turns it into the files in `backend/raw_data/`:

| File | Contents |
|---|---|
| `teams.json` | 30 teams with abbreviations |
| `games.json` | 1,321 games: regular season, play-in and playoffs |
| `players.json` | 582 players with bio (height, weight, position, draft) and box-score averages |
| `possessions.csv.gz` | 262,398 possessions, both five-man units and possession-level stats |
| `shots.csv.gz` | 234,430 field goal attempts with court location and both lineups |

Teams, games and players are loaded into Postgres. Possessions and shots are not: at ~350 MB as tables they
would outgrow a small hosted database, so the backend reads the two `.csv.gz` files straight into memory
(pandas) on its first request and aggregates from there.

How the possessions are built:

- **Lineups**: box-score starters for the first period; for later periods, every player whose first event in
  the period isn't a substitution in, topped up from the previous period. 99.9% of possessions end up with both
  lineups known; the rest are left out.
- **Possessions** end on a made basket (after any and-one), a defensive rebound, a turnover or the end of a period.
- **Validation**: rebuilt scores match the final score exactly in 97.7% of games once technical free throws are
  counted. League offensive rating (115.4), pace (~99) and eFG% (54.4%) line up with the season's real rates.
- **Clutch**: last five minutes of the fourth quarter or overtime with the score within five.

### Approximated stats

Two stats from the original possession format aren't recorded in this dataset, so they are estimated. Both are
marked **≈ Approx.** in the UI and described by `/api/v1/meta`:

- `shot_attempt_points`: points from made field goals plus the and-one free throw that came with them.
- `ft_potential_points`: one potential point per free throw attempted (technicals excluded).

## API

| Endpoint | Returns |
|---|---|
| `GET /api/v1/lineups` | Lineup summaries. `lineup_size` (1-5), `team_id`, `player_ids`, `exclude_player_ids`, `search`, `min_possessions`, `sort_by`, `order`, `limit`, `offset`. Total rows in `X-Total-Count`. |
| `GET /api/v1/lineups/trend` | Month-by-month ratings for one lineup (`team_id`, `player_ids`). |
| `GET /api/v1/players` | Every player's on-court and off-court splits, on/off difference, bio and averages. |
| `GET /api/v1/shots` | Hex-binned shot locations plus zone and shot-type splits vs league, for a lineup's shots (`side=offense`) or its opponents' (`side=defense`). |
| `GET /api/v1/league` | League averages over the filtered games. |
| `GET /api/v1/meta` | Season coverage, data notes and approximation definitions. |
| `GET /api/v1/teams` | All teams. |

Every endpoint also takes the context filters `game_type` (`Regular Season`, `Play-In`, `Playoffs`), `location`
(`home`, `away`), `clutch=1`, `period`, `date_from` and `date_to`.

## Setup

### Database

```
createuser nbaapp --createdb
createdb -O nbaapp nba
psql nba -c "create schema app authorization nbaapp; alter user nbaapp with password 'nba';"
```

### Backend

```
pyenv install 3.12.9
python -m venv .venv
.venv/bin/pip install -r backend/requirements.txt

cd backend
../.venv/bin/python manage.py migrate
PYTHONPATH=. ../.venv/bin/python scripts/ingest_raw_data.py   # teams, games, players (a second)
../.venv/bin/python manage.py runserver                       # http://localhost:8000
```

Tests: `../.venv/bin/python manage.py test app`

### Rebuilding the data (optional)

`backend/raw_data/` is committed, so this is only needed to pick up a newer Kaggle version:

```
.venv/bin/pip install -r backend/requirements-data.txt
cd backend
../.venv/bin/python scripts/build_dataset.py                 # downloads with kagglehub (about 1.8 GB)
../.venv/bin/python scripts/build_dataset.py /path/to/dataset  # or use a copy you already have
```

### Frontend

```
cd frontend
npm install
npm start        # http://localhost:4200
```

## Deploying through Railway

The backend and database run on Railway; the frontend runs on Vercel (`frontend/vercel.json`).

- **Railway**: a Postgres service plus a `backend` service rooted at `backend/`, with
  `DATABASE_URL=${{Postgres.DATABASE_URL}}`. Each deploy runs migrations and `scripts/ingest_raw_data.py`, so
  there is no separate data-loading step. Railway ignored `backend/railway.json` for CLI uploads, so the start
  command is also set as the service variable `RAILPACK_START_CMD` (same command as in `railway.json`). Without GitHub access, deploy from this folder with
  `railway up backend --path-as-root --service backend`.
- **Vercel**: put the backend's public domain in `frontend/src/environments/environment.prod.ts`, then deploy
  `frontend/` (`npx vercel --prod` from that folder, or import the repo with root directory `frontend`).
