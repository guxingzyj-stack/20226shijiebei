import { Link } from "react-router-dom";
import { Trash2 } from "lucide-react";
import { useBetSlip } from "../bet/BetSlipContext";
import { formatDecimal, playTypeLabel, selectionLabel } from "../utils/format";

export function BetSlipCompact() {
  const { legs, removeLeg } = useBetSlip();
  const estimate = legs.reduce((product, leg) => product * Number(leg.odds || 1), 1);
  return (
    <aside className="rounded-lg border border-white/10 bg-white/[0.06] p-4 shadow-soft">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-lg font-semibold text-paper">模拟注单</h2>
        <span className="text-xs text-paper/55">{legs.length}/8 legs</span>
      </div>
      {legs.length === 0 ? (
        <p className="text-sm text-paper/60">从比赛详情页添加虚拟下注选项。</p>
      ) : (
        <div className="space-y-2">
          {legs.map((leg, index) => (
            <div key={`${leg.match_id}-${leg.play_type}-${leg.selection}`} className="rounded-lg bg-pitch/70 p-3">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <div className="text-sm font-medium text-paper">{leg.label || leg.match_id}</div>
                  <div className="text-xs text-paper/55">
                    {playTypeLabel(leg.play_type)} · {selectionLabel(leg.selection)} · {formatDecimal(leg.odds)}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => removeLeg(index)}
                  className="rounded p-1 text-paper/50 hover:bg-white/10 hover:text-paper"
                  aria-label="移除模拟下注选项"
                >
                  <Trash2 size={16} />
                </button>
              </div>
            </div>
          ))}
          <div className="pt-2 text-sm text-paper/70">赔率乘积约 {formatDecimal(estimate)}</div>
        </div>
      )}
      <Link to="/bet" className="mt-4 block rounded-lg bg-gold px-4 py-3 text-center text-sm font-semibold text-pitch">
        去虚拟下注
      </Link>
    </aside>
  );
}
