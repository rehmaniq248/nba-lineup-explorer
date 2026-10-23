import { Routes } from '@angular/router';

export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'lineups-summary' },
  {
    path: 'lineups-summary',
    loadComponent: () =>
      import('./lineups-summary/lineups-summary.component').then((m) => m.LineupsSummaryComponent),
    children: [
      {
        path: '',
        title: 'Overview',
        loadComponent: () => import('./lineups-summary/tabs/overview/overview.component').then((m) => m.OverviewComponent),
      },
      {
        path: 'matchup',
        title: 'Matchup',
        loadComponent: () => import('./lineups-summary/tabs/matchup/matchup.component').then((m) => m.MatchupComponent),
      },
      {
        path: 'shooting',
        title: 'Shooting',
        loadComponent: () => import('./lineups-summary/tabs/shooting/shooting.component').then((m) => m.ShootingComponent),
      },
      {
        path: 'rebounding',
        title: 'Rebounding',
        loadComponent: () =>
          import('./lineups-summary/tabs/rebounding/rebounding.component').then((m) => m.ReboundingComponent),
      },
      {
        path: 'ball-security',
        title: 'Ball security',
        loadComponent: () =>
          import('./lineups-summary/tabs/ball-security/ball-security.component').then((m) => m.BallSecurityComponent),
      },
      {
        path: 'offense-vs-defense',
        title: 'Offense vs. defense',
        loadComponent: () =>
          import('./lineups-summary/tabs/offense-defense/offense-defense.component').then((m) => m.OffenseDefenseComponent),
      },
      {
        path: 'players',
        title: 'Players',
        loadComponent: () => import('./lineups-summary/tabs/players/players.component').then((m) => m.PlayersComponent),
      },
    ],
  },
  {
    path: 'lineups-summary-api',
    loadComponent: () =>
      import('./lineups-summary-response/lineups-summary-response.component').then(
        (m) => m.LineupsSummaryResponseComponent,
      ),
  },
  { path: '**', redirectTo: 'lineups-summary' },
];
