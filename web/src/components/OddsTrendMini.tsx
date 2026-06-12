import type { OddsSnapshot } from "../api/types";
import { formatDateTime } from "../utils/format";

const SERIES = [
  { key: "3", label: "主胜", color: "#f2c14e" },
  { key: "1", label: "平局", color: "#8fd7ff" },
  { key: "0", label: "客胜", color: "#f78fb3" },
];

export function OddsTrendMini({ rows }: { rows: OddsSnapshot[] }) {
  const validRows = rows
    .filter((row) => ["3", "1", "0"].every((key) => Number(row.odds?.[key]) > 0))
    .sort((left, right) => new Date(left.fetched_at).getTime() - new Date(right.fetched_at).getTime());

  if (validRows.length < 2) {
    return <div className="text-sm text-paper/60">赔率历史不足，暂无法绘制走势</div>;
  }

  const width = 300;
  const height = 128;
  const padding = 18;
  const values = validRows.flatMap((row) => SERIES.map((series) => Number(row.odds[series.key])));
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = Math.max(max - min, 0.01);
  const x = (index: number) => padding + (index / Math.max(validRows.length - 1, 1)) * (width - padding * 2);
  const y = (value: number) => height - padding - ((value - min) / span) * (height - padding * 2);
  const lines = SERIES.map((series) => ({
    ...series,
    points: validRows.map((row, index) => `${x(index)},${y(Number(row.odds[series.key]))}`).join(" "),
  }));
  const goalLines = Array.from(new Set(validRows.map((row) => row.goal_line).filter((value) => value !== null && value !== undefined && value !== "")));

  return (
    <div className="space-y-3">
      <svg viewBox={`0 0 ${width} ${height}`} className="h-36 w-full overflow-visible rounded-lg bg-black/15">
        {[0, 1, 2].map((tick) => (
          <line
            key={tick}
            x1={padding}
            x2={width - padding}
            y1={padding + tick * ((height - padding * 2) / 2)}
            y2={padding + tick * ((height - padding * 2) / 2)}
            stroke="rgba(255,255,255,0.08)"
          />
        ))}
        {lines.map((line) => (
          <polyline key={line.key} points={line.points} fill="none" stroke={line.color} strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
        ))}
      </svg>
      <div className="flex flex-wrap gap-3 text-xs text-paper/60">
        {SERIES.map((series) => (
          <span key={series.key} className="inline-flex items-center gap-1">
            <span className="h-2 w-2 rounded-full" style={{ backgroundColor: series.color }} />
            {series.label}
          </span>
        ))}
      </div>
      <div className="text-xs text-paper/45">
        {formatDateTime(validRows[0].fetched_at)} 至 {formatDateTime(validRows[validRows.length - 1].fetched_at)}
      </div>
      <div className="text-xs text-paper/50">{goalLines.length ? `让球线变化：${goalLines.join(" → ")}` : "暂无让球线变化数据"}</div>
    </div>
  );
}
