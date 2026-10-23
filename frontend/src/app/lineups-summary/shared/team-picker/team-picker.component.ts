import { Component, ElementRef, computed, inject, input, output, signal } from '@angular/core';

import { Team } from '../../../_services/lineup.models';

let nextId = 0;

/**
 * Searchable team filter: type part of a city, nickname or abbreviation, then pick with the mouse or the
 * arrow keys and Enter. An empty pick means every team.
 */
@Component({
  selector: 'team-picker',
  templateUrl: './team-picker.component.html',
  styleUrl: './team-picker.component.scss',
  host: { '(document:click)': 'onDocumentClick($event)' },
})
export class TeamPickerComponent {
  private readonly host = inject(ElementRef<HTMLElement>);

  readonly teams = input.required<Team[]>();
  readonly teamId = input('');
  readonly teamChange = output<string>();

  readonly listId = `team-picker-${nextId++}`;
  readonly open = signal(false);
  readonly query = signal('');
  readonly active = signal(0);

  readonly selected = computed(() => this.teams().find((team) => team.team_id === this.teamId()) ?? null);

  /** "All teams" first, then the teams that match what has been typed. */
  readonly options = computed<(Team | null)[]>(() => {
    const query = this.query().trim().toLowerCase();
    const matches = this.teams().filter(
      (team) =>
        !query ||
        team.name.toLowerCase().includes(query) ||
        team.abbreviation.toLowerCase().startsWith(query),
    );
    return query ? matches : [null, ...matches];
  });

  readonly inputValue = computed(() => (this.open() ? this.query() : (this.selected()?.name ?? '')));

  onInput(value: string): void {
    this.query.set(value);
    this.active.set(0);
    this.open.set(true);
  }

  onFocus(): void {
    this.query.set('');
    this.active.set(0);
    this.open.set(true);
  }

  onKeydown(event: KeyboardEvent): void {
    const count = this.options().length;
    switch (event.key) {
      case 'ArrowDown':
        event.preventDefault();
        this.open.set(true);
        this.active.set(count ? (this.active() + 1) % count : 0);
        break;
      case 'ArrowUp':
        event.preventDefault();
        this.active.set(count ? (this.active() - 1 + count) % count : 0);
        break;
      case 'Enter':
        if (this.open() && count) {
          event.preventDefault();
          this.choose(this.options()[this.active()]);
        }
        break;
      case 'Escape':
        this.close();
        break;
    }
  }

  choose(team: Team | null): void {
    this.teamChange.emit(team?.team_id ?? '');
    this.close();
  }

  clear(): void {
    this.choose(null);
  }

  optionId(index: number): string {
    return `${this.listId}-${index}`;
  }

  onDocumentClick(event: MouseEvent): void {
    if (!this.host.nativeElement.contains(event.target as Node)) {
      this.close();
    }
  }

  private close(): void {
    this.open.set(false);
    this.query.set('');
  }
}
