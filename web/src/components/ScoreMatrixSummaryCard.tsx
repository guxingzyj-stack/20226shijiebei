import { formatDecimal, formatPercent } from "../utils/format";
import { summarizeScoreMatrix } from "../utils/matchAnalytics";

export function ScoreMatrixSummaryCard({ matrix }: { matrix?: number[][] | null }) {
  const summary = summarizeScoreMatrix(matrix);
  if (!summary) {
    return <div className="text-sm text-paper/60">比分矩阵不足，暂无法生成关键数字。</div>;
  }

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-3 gap-2">
        <Metric label="主队期望进球" value={formatDecimal(summary.expectedHome)} />
        <Metric label="客队期望进球" value={formatDecimal(summary.expectedAway)} />
        <Metric label="总期望进球" value={formatDecimal(summary.expectedTotal)} />
      </div>
      <div className="space-y-2">
        <div className="text-xs text-paper/50">最可能比分 Top 3</div>
        {summary.topScores.map((score) => (
          <div key={`${score.home}-${score.away}`} className="flex items-center justify-between rounded-lg bg-white/5 px-3 py-2 text-sm">
            <span className="font-semibold">{score.home}:{score.away}</span>
            <span className="text-paper/60">{formatPercent(score.probability)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-white/5 p-3">
      <div className="text-[11px] text-paper/45">{label}</div>
      <div className="mt-1 text-lg font-semibold text-gold">{value}</div>
    </div>
  );
}
