# -*- coding: utf-8 -*-
import datetime
import logging

from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from app.dbmodels.models import Team
from app.helpers.data import GAME_TYPES, LOCATIONS, Filters
from app.helpers.league import get_league_averages, get_meta
from app.helpers.lineups import get_lineup_league_summary_stats, get_lineup_trend
from app.helpers.players import get_player_on_off_stats
from app.helpers.shots import get_shot_chart

LOGGER = logging.getLogger('django')


def _parse_int_query_param(request, key, default, minimum=None, maximum=None):
    """Parse an int query param with optional bounds."""
    raw_value = request.query_params.get(key, default)
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        value = default

    if value is None:
        return None
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def _parse_id(raw_value, key):
    """NBA ids (teams, players, games) are positive integers."""
    value = str(raw_value).strip()
    if not value.isdigit():
        raise ValidationError({key: f'"{raw_value}" is not a valid id'})
    return value


def _parse_id_list(request, key):
    raw_value = request.query_params.get(key)
    if not raw_value:
        return []
    return [_parse_id(part, key) for part in raw_value.split(',') if part.strip()]


def _parse_optional_id(request, key):
    raw_value = request.query_params.get(key)
    return _parse_id(raw_value, key) if raw_value else None


def _parse_optional_date(request, key):
    raw_value = request.query_params.get(key)
    if not raw_value:
        return None
    try:
        return datetime.date.fromisoformat(raw_value).isoformat()
    except ValueError:
        raise ValidationError({key: 'Expected a date formatted YYYY-MM-DD'})


def _parse_choice(request, key, choices):
    raw_value = request.query_params.get(key)
    if not raw_value:
        return None
    if raw_value not in choices:
        raise ValidationError({key: f'Expected one of: {", ".join(choices)}'})
    return raw_value


def _parse_bool(request, key):
    return request.query_params.get(key, '').lower() in ('1', 'true', 'yes')


def _context_options(request):
    """Filters shared by every endpoint: which part of the season, which games, which minutes."""
    return {
        'game_type': _parse_choice(request, 'game_type', GAME_TYPES),
        'date_from': _parse_optional_date(request, 'date_from'),
        'date_to': _parse_optional_date(request, 'date_to'),
        'period': _parse_int_query_param(request, key='period', default=None, minimum=1) or None,
        'clutch': _parse_bool(request, 'clutch'),
        'location': _parse_choice(request, 'location', LOCATIONS),
    }


def _paging_options(request, default_sort):
    limit = request.query_params.get('limit')
    return {
        'min_possessions': _parse_int_query_param(request, key='min_possessions', default=0, minimum=0),
        'search': request.query_params.get('search', ''),
        'sort_by': request.query_params.get('sort_by', default_sort),
        'order': request.query_params.get('order', 'desc').lower(),
        'limit': _parse_int_query_param(request, key='limit', default=None, minimum=1) if limit else None,
        'offset': _parse_int_query_param(request, key='offset', default=0, minimum=0),
    }


def _get_lineup_query_options(request):
    """Translate query params into keyword args for get_lineup_league_summary_stats."""
    return {
        'lineup_size': _parse_int_query_param(
            request,
            key='lineup_size',
            default=5,
            minimum=1,
            maximum=5,
        ),
        'team_id': _parse_optional_id(request, 'team_id'),
        'player_ids': _parse_id_list(request, 'player_ids'),
        'exclude_player_ids': _parse_id_list(request, 'exclude_player_ids'),
        'game_id': _parse_optional_id(request, 'game_id'),
        **_context_options(request),
        **_paging_options(request, 'net_rating'),
    }


def _paged_response(rows, total):
    response = Response(rows)
    response['X-Total-Count'] = total
    return response


class LineupsLeagueSummary(APIView):
    logger = LOGGER

    def get(self, request):
        """Return the league-wide lineup summary.

        The body is a list of lineups; the row count before limit/offset is in the X-Total-Count header.
        """
        query_options = _get_lineup_query_options(request)
        try:
            lineups, total = get_lineup_league_summary_stats(**query_options)
        except ValueError as error:
            raise ValidationError(str(error))
        return _paged_response(lineups, total)


class LineupTrend(APIView):
    def get(self, request):
        """Month-by-month ratings for one lineup, given its `team_id` and `player_ids`."""
        team_id = _parse_optional_id(request, 'team_id')
        player_ids = _parse_id_list(request, 'player_ids')
        if not team_id or not player_ids:
            raise ValidationError('team_id and player_ids are required')
        options = _context_options(request)
        filters = Filters(**{key: value for key, value in options.items()})
        return Response(get_lineup_trend(player_ids, team_id, filters))


class Players(APIView):
    def get(self, request):
        """Every player's on-court and off-court splits, bio and box-score averages."""
        options = {
            'team_id': _parse_optional_id(request, 'team_id'),
            'player_ids': _parse_id_list(request, 'player_ids'),
            **_context_options(request),
            **_paging_options(request, 'on_off_net'),
        }
        try:
            players, total = get_player_on_off_stats(**options)
        except ValueError as error:
            raise ValidationError(str(error))
        return _paged_response(players, total)


class Shots(APIView):
    def get(self, request):
        """Binned shot locations plus zone and shot-type splits for a lineup, team, or the whole league."""
        try:
            chart = get_shot_chart(
                player_ids=_parse_id_list(request, 'player_ids'),
                team_id=_parse_optional_id(request, 'team_id'),
                side=request.query_params.get('side', 'offense'),
                **_context_options(request),
            )
        except ValueError as error:
            raise ValidationError(str(error))
        return Response(chart)


class League(APIView):
    def get(self, request):
        """League averages over the games the current filters cover."""
        options = _context_options(request)
        options.pop('location')
        return Response(get_league_averages(Filters(**options)))


class Meta(APIView):
    def get(self, request):
        """Season coverage, data notes, and the definitions of approximated stats."""
        return Response(get_meta())


class Teams(APIView):
    def get(self, request):
        """Return every team, for populating filter dropdowns."""
        return Response([
            {'team_id': str(team.id), 'name': team.name, 'city': team.city, 'nickname': team.nickname,
             'abbreviation': team.abbreviation}
            for team in Team.objects.order_by('name')
        ])
