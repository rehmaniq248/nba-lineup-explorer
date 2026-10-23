import { Component, computed, input } from '@angular/core';

import { ShotChart } from '../../../_services/lineup.models';
import { pct, scaleColor, signed } from '../../../_services/lineup.utils';

// Drawing units are tenths of a foot on a 50 ft wide, 47 ft deep half court, basket at the top.
const UNIT = 10;
const WIDTH = 50 * UNIT;
const DEPTH = 47 * UNIT;
const BASKET_Y = 5.25 * UNIT;
// FG% this far above or below league average at a spot saturates the colour.
const VS_LEAGUE_SATURATION = 0.12;
// The smallest hexagon drawn, as a share of a full one, so single shots stay visible.
const MIN_HEX_SCALE = 0.32;

interface HexView {
  key: string;
  points: string;
  fill: string;
  title: string;
}

const hexPoints = (cx: number, cy: number, radius: number): string =>
  Array.from({ length: 6 }, (_, index) => {
    const angle = (Math.PI / 180) * (60 * index - 30);
    return `${(cx + radius * Math.cos(angle)).toFixed(1)},${(cy + radius * Math.sin(angle)).toFixed(1)}`;
  }).join(' ');

/**
 * Half-court shot chart. Each hexagon is a patch of floor: its size is how often the lineup shot from there and
 * its colour is FG% against the league average for that zone. For opponents' shots the colours flip, so blue
 * always means good for the selected lineup.
 */
@Component({
  selector: 'shot-chart',
  templateUrl: './shot-chart.component.html',
  styleUrl: './shot-chart.component.scss',
})
export class ShotChartComponent {
  readonly chart = input.required<ShotChart>();
  readonly label = input.required<string>();

  readonly width = WIDTH;
  readonly depth = DEPTH;
  readonly basketY = BASKET_Y;
  readonly unit = UNIT;

  /** The three-point line: straight in the corners (3 ft from each sideline), then a 23.75 ft arc. */
  readonly threePath = (() => {
    const radius = 23.75 * UNIT;
    const cornerX = 3 * UNIT;
    const cornerY = BASKET_Y + Math.sqrt(radius ** 2 - (WIDTH / 2 - cornerX) ** 2);
    return `M${cornerX} 0 V${cornerY.toFixed(1)} A${radius} ${radius} 0 0 0 ${WIDTH - cornerX} ${cornerY.toFixed(1)} V0`;
  })();

  readonly restrictedPath = `M${WIDTH / 2 - 4 * UNIT} ${BASKET_Y} A${4 * UNIT} ${4 * UNIT} 0 0 0 ${WIDTH / 2 + 4 * UNIT} ${BASKET_Y}`;

  readonly hexes = computed<HexView[]>(() => {
    const chart = this.chart();
    const flip = chart.side === 'defense' ? -1 : 1;
    const maxAttempts = Math.max(1, ...chart.hexes.map((hex) => hex.attempted));
    const full = chart.hex_size * UNIT;
    return chart.hexes.map((hex) => {
      const scale = MIN_HEX_SCALE + (1 - MIN_HEX_SCALE) * Math.sqrt(hex.attempted / maxAttempts);
      // Mirror across so the shooter's left corner is on the left with the basket at the top.
      const cx = WIDTH - hex.x * UNIT;
      const cy = hex.y * UNIT;
      return {
        key: `${hex.x}:${hex.y}`,
        points: hexPoints(cx, cy, full * scale * 0.98),
        fill: scaleColor((flip * hex.vs_league) / VS_LEAGUE_SATURATION),
        title: `${hex.made}/${hex.attempted} · ${pct(hex.pct, 0)} (${signed(hex.vs_league * 100, 0)} vs league)`,
      };
    });
  });

  readonly legend = [-1, -0.5, 0, 0.5, 1].map((t) => ({
    color: scaleColor(t),
    label: t === 0 ? 'avg' : `${signed(t * VS_LEAGUE_SATURATION * 100, 0)}`,
  }));
}
