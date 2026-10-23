"""backend URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/3.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.urls import re_path
from app.views import lineups

urlpatterns = [
    re_path(
        r'^api/v1/lineups$',
        lineups.LineupsLeagueSummary.as_view(),
        name='lineups_summary',
    ),
    re_path(r'^api/v1/lineups/trend$', lineups.LineupTrend.as_view(), name='lineup_trend'),
    re_path(r'^api/v1/players$', lineups.Players.as_view(), name='players'),
    re_path(r'^api/v1/shots$', lineups.Shots.as_view(), name='shots'),
    re_path(r'^api/v1/league$', lineups.League.as_view(), name='league'),
    re_path(r'^api/v1/meta$', lineups.Meta.as_view(), name='meta'),
    re_path(r'^api/v1/teams$', lineups.Teams.as_view(), name='teams'),
]
