import { Fragment } from "react";
import { formatPercent } from "../utils/format";

export function ScoreMatrix({ matrix }: { matrix?: number[][] | null }) {
  if (!matrix?.length) {
    return <div className="rounded-lg border border-white/10 p-4 text-sm text-paper/60">比分矩阵生成中</div>;
  }
  const max = Math.max(...matrix.flat());
  return (
    <div className="overflow-x-auto rounded-lg border border-white/10 bg-black/10 p-3">
      <div className="grid min-w-[560px] gap-1" style={{ gridTemplateColumns: `40px repeat(${matrix[0].length}, minmax(36px, 1fr))` }}>
        <div />
        {matrix[0].map((_, away) => (
          <div key={`a-${away}`} className="text-center text-xs text-paper/45">
            {away}
          </div>
        ))}
        {matrix.map((row, home) => (
          <Fragment key={`row-${home}`}>
            <div key={`h-${home}`} className="flex items-center justify-center text-xs text-paper/45">
              {home}
            </div>
            {row.map((value, away) => {
              const intensity = max > 0 ? value / max : 0;
              return (
                <div
                  key={`${home}-${away}`}
                  className="rounded px-1 py-2 text-center text-[10px] text-paper"
                  style={{ backgroundColor: `rgba(232, 179, 60, ${0.08 + intensity * 0.62})` }}
                  title={`${home}:${away} ${formatPercent(value)}`}
                >
                  {formatPercent(value)}
                </div>
              );
            })}
          </Fragment>
        ))}
      </div>
    </div>
  );
}
