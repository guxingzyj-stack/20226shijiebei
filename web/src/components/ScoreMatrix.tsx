import { Fragment } from "react";
import { formatPercent } from "../utils/format";
import { normalizeScoreMatrix, scoreInMatrix } from "../utils/matchAnalytics";

type ScoreMatrixProps = {
  matrix?: number[][] | null;
  resultHome?: number | null;
  resultAway?: number | null;
  matchStatus?: string;
};

export function ScoreMatrix({ matrix, resultHome, resultAway, matchStatus }: ScoreMatrixProps) {
  const normalized = normalizeScoreMatrix(matrix);
  if (!normalized?.length) {
    return <div className="rounded-lg border border-white/10 p-4 text-sm text-paper/60">比分矩阵生成中</div>;
  }
  const max = Math.max(...normalized.flat());
  const hasResult = resultHome !== null && resultHome !== undefined && resultAway !== null && resultAway !== undefined;
  const resultInside = scoreInMatrix(normalized, resultHome, resultAway);
  const finishedMissingResult = ["finished", "completed"].includes(matchStatus || "") && !hasResult;
  return (
    <div className="space-y-3">
      <div className="overflow-x-auto rounded-lg border border-white/10 bg-black/10 p-3">
        <div className="grid min-w-[560px] gap-1" style={{ gridTemplateColumns: `40px repeat(${normalized[0].length}, minmax(36px, 1fr))` }}>
          <div />
          {normalized[0].map((_, away) => (
            <div key={`a-${away}`} className="text-center text-xs text-paper/45">
              {away}
            </div>
          ))}
          {normalized.map((row, home) => (
            <Fragment key={`row-${home}`}>
              <div key={`h-${home}`} className="flex items-center justify-center text-xs text-paper/45">
                {home}
              </div>
              {row.map((value, away) => {
                const intensity = max > 0 ? value / max : 0;
                const isResult = resultInside && resultHome === home && resultAway === away;
                return (
                  <div
                    key={`${home}-${away}`}
                    className={`rounded px-1 py-2 text-center text-[10px] text-paper ${isResult ? "ring-2 ring-emerald-300" : ""}`}
                    style={{ backgroundColor: `rgba(232, 179, 60, ${0.08 + intensity * 0.62})` }}
                    title={`${home}:${away} ${formatPercent(value)}${isResult ? "，最终比分" : ""}`}
                  >
                    {formatPercent(value)}
                  </div>
                );
              })}
            </Fragment>
          ))}
        </div>
      </div>
      {finishedMissingResult ? <div className="text-sm text-gold">赛果回填中</div> : null}
      {hasResult && !resultInside ? <div className="text-sm text-gold">最终比分超出当前矩阵范围</div> : null}
    </div>
  );
}
