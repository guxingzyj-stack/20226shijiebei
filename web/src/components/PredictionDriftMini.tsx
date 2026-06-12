import type { PredictionHistoryResponse } from "../api/types";
import { formatDateTime, formatPercent } from "../utils/format";
import { asProbability } from "../utils/matchAnalytics";

const SERIES = [
  { key: "p_home", label: "主胜", color: "#f2c14e" },
  { key: "p_draw", label: "平局", color: "#8fd7ff" },
  { key: "p_away", label: "客胜", color: "#f78fb3" },
] as const;

export function PredictionDriftMini({ data }: { data?: PredictionHistoryResponse | null }) {
  const points = data?.points || [];
  if (!points.length) {
    return <div className="text-sm text-paper/60">暂无模型概率历史。</div>;
  }
  if (points.length < 2) {
    return <div className="text-sm text-paper/60">当前只有一次模型快照，暂无法形成趋势。</div>;
  }

  const width = 300;
  const height = 128;
  const padding = 18;
  const sorted = [...points].sort((left, right) => new Date(left.created_at).getTime() - new Date(right.created_at).getTime());
  const x = (index: number) => padding + (index / Math.max(sorted.length - 1, 1)) * (width - padding * 2);
  const y = (value: number) => height - padding - value * (height - padding * 2);

  return (
    <div className="space-y-3">
      <svg viewBox={`0 0 ${width} ${height}`} className="h-36 w-full rounded-lg bg-black/15">
        {[0.25, 0.5, 0.75].map((tick) => (
          <line key={tick} x1={padding} x2={width - padding} y1={y(tick)} y2={y(tick)} stroke="rgba(255,255,255,0.08)" />
        ))}
        {SERIES.map((series) => (
          <polyline
            key={series.key}
            points={sorted.map((point, index) => `${x(index)},${y(asProbability(point[series.key]))}`).join(" ")}
            fill="none"
            stroke={series.color}
            strokeWidth="2.4"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
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
        {formatDateTime(sorted[0].created_at)} 至 {formatDateTime(sorted[sorted.length - 1].created_at)}，最新主胜 {formatPercent(asProbability(sorted[sorted.length - 1].p_home))}
      </div>
    </div>
  );
}
