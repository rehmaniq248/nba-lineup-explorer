import { Component, computed, input } from '@angular/core';

export type SplitFormat = 'pct' | 'ppp' | 'per100';

export interface SplitRow {
  label: string;
  left: number;
  right: number;
  format: SplitFormat;
  /** The lower value wins the row (turnovers) instead of the higher. */
  lowerWins?: boolean;
  /** Set when the stat is estimated rather than recorded; the text explains how, shown on hover. */
  approx?: string;
}

interface RowView {
  label: string;
  approx?: string;
  leftText: string;
  rightText: string;
  leftShare: number;
  winner: 'left' | 'right' | 'even';
}

const format = (value: number, kind: SplitFormat): string => {
  switch (kind) {
    case 'pct':
      return `${(value * 100).toFixed(1)}%`;
    case 'per100':
      return (value * 100).toFixed(1);
    default:
      return value.toFixed(2);
  }
};

/** Two-sided bars: the left value against the right value, split in proportion, with the winner brighter. */
@Component({
  selector: 'split-bars',
  templateUrl: './split-bars.component.html',
  styleUrl: './split-bars.component.scss',
})
export class SplitBarsComponent {
  readonly rows = input.required<SplitRow[]>();
  readonly leftLabel = input.required<string>();
  readonly rightLabel = input('Opponents');
  readonly note = input('The brighter side of each bar won that matchup.');

  readonly views = computed<RowView[]>(() =>
    this.rows().map((row) => {
      const total = row.left + row.right;
      const better = row.lowerWins ? row.left < row.right : row.left > row.right;
      const worse = row.lowerWins ? row.left > row.right : row.left < row.right;
      return {
        label: row.label,
        approx: row.approx,
        leftText: format(row.left, row.format),
        rightText: format(row.right, row.format),
        leftShare: total ? (row.left / total) * 100 : 50,
        winner: better ? 'left' : worse ? 'right' : 'even',
      };
    }),
  );
}
