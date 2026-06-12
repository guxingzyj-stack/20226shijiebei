import type { OddsMap, Prediction } from "../api/types";
import { formatPercent } from "../utils/format";
import { marketProbabilities, predictionProbabilities } from "../utils/matchAnalytics";

const ROWS = [
  { key: "home", label: "主胜" },
  { key: "draw", label: "平局" },
  { key: "away", label: "客胜" },
] as const;

export function MarketModelCompare({ prediction, odds }: { prediction?: Prediction | null; odds?: OddsMap | null }) {
  const model = predictionProbabilities(prediction);
  const market = marketProbabilities(odds);
  if (!model || !market) {
    return <div className="text-sm text-paper/60">模型或市场概率不足，暂无法对比。</div>;
  }

  return (
    <div className="space-y-3">
      {ROWS.map((row) => (
        <div key={row.key} className="space-y-1">
          <div className="flex items-center justify-between text-xs text-paper/60">
            <span>{row.label}</span>
            <span>
              模型 {formatPercent(model[row.key])} / 市场 {formatPercent(market[row.key])}
            </span>
          </div>
          <div className="grid gap-1">
            <div className="h-2 overflow-hidden rounded-full bg-white/10">
              <div className="h-full rounded-full bg-gold" style={{ width: `${Math.min(model[row.key] * 100, 100)}%` }} />
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-white/10">
              <div className="h-full rounded-full bg-sky-300" style={{ width: `${Math.min(market[row.key] * 100, 100)}%` }} />
            </div>
          </div>
        </div>
      ))}
      <div className="flex gap-3 text-xs text-paper/45">
        <span className="inline-flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-gold" />模型</span>
        <span className="inline-flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-sky-300" />市场隐含概率</span>
      </div>
    </div>
  );
}
