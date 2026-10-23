import { Component, inject } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

import { ThemeService } from './_services/theme.service';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, RouterLink, RouterLinkActive],
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
export class App {
  readonly themeService = inject(ThemeService);

  readonly tabs = [
    { path: '', label: 'Overview' },
    { path: '/matchup', label: 'Matchup' },
    { path: '/shooting', label: 'Shooting' },
    { path: '/rebounding', label: 'Rebounding' },
    { path: '/ball-security', label: 'Ball security' },
    { path: '/offense-vs-defense', label: 'Offense vs. defense' },
  ];

  readonly playerTabs = [{ path: '/players', label: 'On / off' }];
}
