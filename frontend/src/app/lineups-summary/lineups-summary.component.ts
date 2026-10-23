import { Component, inject } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { NavigationEnd, Router, RouterOutlet } from '@angular/router';
import { filter, map, startWith } from 'rxjs/operators';

import { GAME_TYPES, LOCATIONS, LineupsStore } from '../_services/lineups.store';
import { TeamPickerComponent } from './shared/team-picker/team-picker.component';

/** Shell for every dashboard tab: the filters live here, and the active tab renders in the outlet. */
@Component({
  selector: 'lineups-summary-component',
  imports: [FormsModule, RouterOutlet, TeamPickerComponent],
  templateUrl: './lineups-summary.component.html',
  styleUrl: './lineups-summary.component.scss',
})
export class LineupsSummaryComponent {
  readonly store = inject(LineupsStore);
  private readonly router = inject(Router);

  readonly sizes = [1, 2, 3, 4, 5];
  readonly gameTypes = GAME_TYPES;
  readonly locations = LOCATIONS;

  /** The Players tab loads its own data, so lineup-only filters and lineup loading states are hidden there. */
  readonly playersTab = toSignal(
    this.router.events.pipe(
      filter((event) => event instanceof NavigationEnd),
      startWith(null),
      map(() => this.router.url.split('?')[0].endsWith('/players')),
    ),
    { initialValue: false },
  );
}
