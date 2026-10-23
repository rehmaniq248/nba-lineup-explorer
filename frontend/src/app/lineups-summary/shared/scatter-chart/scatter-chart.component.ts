import { Component, computed, input, output } from '@angular/core';

import { LineupSummary } from '../../../_services/lineup.models';
import { lineupKey, num, scaleColor, signed } from '../../../_services/lineup.utils';

const WIDTH = 640;
const HEIGHT = 380;
const PAD = { left: 52, right: 20, top: 20, bottom: 44 };
// A net rating of ±30 per 100 possessions saturates the bubble colour.
const NET_SATURATION = 30;

interface Bubble {
  key: string;
  lineup: LineupSummary;
  x: number;
  y: number;
  r: number;
  fill: string;
  title: string;
}

interface Tick {
  pos: number;
  label: string;
}

/** One bubble per lineup, sized by possessions and coloured by net rating. Any two metrics can be plotted. */
@Component({
  selector: 'scatter-chart',
  templateUrl: './scatter-chart.component.html',
  styleUrl: './scatter-chart.component.scss',
})
export class ScatterChartComponent {
  readonly lineups = input.required<LineupSummary[]>();
  readonly selectedKey = input<string | null>(null);
  readonly xKey = input.required<string>();
  readonly yKey = input.required<string>();
  readonly xLabel = input.required<string>();
  readonly yLabel = input.required<string>();
  /** Values are fractions shown as percentages. `xPercent` / `yPercent` override it for one axis. */
  readonly percent = input(false);
  readonly xPercent = input<boolean | null>(null);
  readonly yPercent = input<boolean | null>(null);
  /** Custom x tick text, e.g. heights in feet and inches. */
  readonly xFormat = input<((value: number) => string) | null>(null);
  /** The lowest y value is best, so it is drawn at the top. */
  readonly lowerYBetter = input(false);
  /** Corner captions: top-left, top-right, bottom-left, bottom-right. */
  readonly quadrants = input<[string, string, string, string]>(['', '', '', '']);
  readonly selectLineup = output<LineupSummary>();

  readonly width = WIDTH;
  readonly height = HEIGHT;
  readonly plot = { left: PAD.left, right: WIDTH - PAD.right, top: PAD.top, bottom: HEIGHT - PAD.bottom };

  private readonly xIsPercent = computed(() => this.xPercent() ?? this.percent());
  private readonly yIsPercent = computed(() => this.yPercent() ?? this.percent());

  private readonly points = computed(() =>
    this.lineups().map((lineup) => ({
      lineup,
      x: num(lineup, this.xKey()) * (this.xIsPercent() ? 100 : 1),
      y: num(lineup, this.yKey()) * (this.yIsPercent() ? 100 : 1),
    })),
  );

  private readonly domain = computed(() => {
    const points = this.points();
    if (!points.length) {
      return { xMin: 0, xMax: 100, yMin: 0, yMax: 100 };
    }
    const span = (values: number[], percent: boolean) => {
      const min = Math.min(...values);
      const max = Math.max(...values);
      const pad = Math.max(percent ? 2 : 1, (max - min) * 0.1);
      return [Math.floor(min - pad), Math.ceil(max + pad)];
    };
    const [xMin, xMax] = span(points.map((point) => point.x), this.xIsPercent());
    const [yMin, yMax] = span(points.map((point) => point.y), this.yIsPercent());
    return { xMin, xMax, yMin, yMax };
  });

  private readonly toX = (value: number): number => {
    const { xMin, xMax } = this.domain();
    return this.plot.left + ((value - xMin) / (xMax - xMin)) * (this.plot.right - this.plot.left);
  };

  private readonly toY = (value: number): number => {
    const { yMin, yMax } = this.domain();
    const fraction = (value - yMin) / (yMax - yMin);
    const fromTop = this.lowerYBetter() ? fraction : 1 - fraction;
    return this.plot.top + fromTop * (this.plot.bottom - this.plot.top);
  };

  /** Possession-weighted means split the chart into quadrants. */
  readonly center = computed(() => {
    const points = this.points();
    const weight = points.reduce((sum, point) => sum + point.lineup.total_possessions, 0);
    if (!weight) {
      return null;
    }
    const mean = (pick: (point: { x: number; y: number }) => number) =>
      points.reduce((sum, point) => sum + pick(point) * point.lineup.total_possessions, 0) / weight;
    return { x: this.toX(mean((point) => point.x)), y: this.toY(mean((point) => point.y)) };
  });

  readonly bubbles = computed<Bubble[]>(() => {
    const maxPossessions = Math.max(1, ...this.lineups().map((row) => row.total_possessions));
    const selected = this.selectedKey();
    return this.points()
      .map(({ lineup, x, y }) => ({
        key: lineupKey(lineup),
        lineup,
        x: this.toX(x),
        y: this.toY(y),
        r: 4 + 10 * Math.sqrt(lineup.total_possessions / maxPossessions),
        fill: scaleColor(lineup.net_rating / NET_SATURATION),
        title: `${lineup.players.map((p) => p.name).join(', ')}\n${this.xLabel()}: ${this.tickLabel(x, 'x')} · ${this.yLabel()}: ${this.tickLabel(y, 'y')}\nNet ${signed(lineup.net_rating)} · ${lineup.total_possessions} possessions`,
      }))
      // Draw the selected bubble last so it sits on top.
      .sort((a, b) => Number(a.key === selected) - Number(b.key === selected));
  });

  private tickLabel(value: number, axis: 'x' | 'y'): string {
    const custom = axis === 'x' ? this.xFormat() : null;
    if (custom) {
      return custom(value);
    }
    const rounded = Math.round(value * 10) / 10;
    return (axis === 'x' ? this.xIsPercent() : this.yIsPercent()) ? `${rounded}%` : String(rounded);
  }

  private ticks(min: number, max: number, pos: (value: number) => number, axis: 'x' | 'y'): Tick[] {
    const rough = (max - min) / 6;
    const step = [1, 2, 5, 10, 20, 25, 50].find((candidate) => candidate >= rough) ?? 50;
    const ticks: Tick[] = [];
    for (let value = Math.ceil(min / step) * step; value <= max; value += step) {
      ticks.push({ pos: pos(value), label: this.tickLabel(value, axis) });
    }
    return ticks;
  }

  readonly xTicks = computed(() => this.ticks(this.domain().xMin, this.domain().xMax, this.toX, 'x'));
  readonly yTicks = computed(() => this.ticks(this.domain().yMin, this.domain().yMax, this.toY, 'y'));
}
