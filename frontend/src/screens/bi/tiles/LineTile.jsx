// LineTile.jsx — v0.8.6 (②b) 折线板块。SQL rows 直喂 Shared LineChart（首键=x，余数值列=系列）。
import { LineChart } from '../../../Shared.jsx';
import { Card, TileState } from './_shared.jsx';
import { parseTile } from './tile_data.js';

export function LineTile({ T, tile }) {
  const { rows, error } = parseTile(tile);
  if (error || rows.length < 2) return <Card T={T} title={tile.title}><TileState T={T} error={error} /></Card>;
  return <Card T={T} title={tile.title}><LineChart data={rows} height={230} stroke={T.accent} /></Card>;
}
