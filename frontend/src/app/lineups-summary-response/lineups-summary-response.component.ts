import { ChangeDetectorRef, Component, OnInit, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';

import { DatasetMeta } from '../_services/lineup.models';
import { LineupsService } from '../_services/lineups.service';

interface LineupSizeOption {
  value: number;
  label: string;
}

@Component({
  selector: 'lineups-summary-response-component',
  imports: [FormsModule, MatFormFieldModule, MatSelectModule],
  templateUrl: './lineups-summary-response.component.html',
  styleUrl: './lineups-summary-response.component.scss',
})
export class LineupsSummaryResponseComponent implements OnInit {
  private readonly lineupsService = inject(LineupsService);
  private readonly cdr = inject(ChangeDetectorRef);

  readonly lineupSizes: LineupSizeOption[] = [
    { value: 5, label: '5 players' },
    { value: 4, label: '4 players' },
    { value: 3, label: '3 players' },
    { value: 2, label: '2 players' },
    { value: 1, label: '1 player' },
  ];

  leagueLineupSize = 5;
  leagueEndpoint = '';
  leagueApiResponse = '';
  meta: DatasetMeta | null = null;
  approximations: { key: string; text: string }[] = [];

  ngOnInit(): void {
    this.fetchLeagueApiResponse();
    this.lineupsService.getMeta().subscribe({
      next: (meta) => {
        this.meta = meta;
        this.approximations = Object.entries(meta.approximations).map(([key, text]) => ({ key, text }));
        this.cdr.detectChanges();
      },
      error: () => undefined,
    });
  }

  changeLeagueLineupSize(): void {
    this.fetchLeagueApiResponse();
  }

  private fetchLeagueApiResponse(): void {
    this.lineupsService.getLineupsLeagueSummary(this.leagueLineupSize).subscribe({
      next: (data) => {
        this.leagueEndpoint = data.endpoint;
        this.leagueApiResponse = JSON.stringify(data.apiResponse, null, 2);
        this.cdr.detectChanges();
      },
      error: (err) => {
        this.leagueEndpoint = 'error';
        this.leagueApiResponse = JSON.stringify(err, null, 2);
        this.cdr.detectChanges();
      },
    });
  }
}
