import type { Prediction } from "../api/types";
import { formatPercent, toNumber } from "../utils/format";

export function ProbabilityBar({ prediction }: { prediction?: Prediction | null }) {
  if (!prediction) {
    return <div className="text-sm text-paper/60">模型预测生成中</div>;
  }
  const home = toNumber(prediction.p_home);
  const draw = toNumber(prediction.p_draw);
  const away = toNumber(prediction.p_away);
  const total = Math.max(home + draw + away, 0.0001);
  const items = [
    { label: "主胜", value: home, className: "bg-gold" },
    { label: "平", value: draw, className: "bg-paper/70" },
    { label: "客胜", value: away, className: "bg-danger" },
  ];
  return (
    <div className="space-y-2">
      <div className="flex h-2 overflow-hidden rounded-full bg-white/10">
        {items.map((item) => (
          <div key={item.label} className={item.className} style={{ width: `${(item.value / total) * 100}%` }} />
        ))}
      </div>
      <div className="grid grid-cols-3 gap-2 text-xs text-paper/70">
        {items.map((item) => (
          <div key={item.label}>
            <span className="block text-paper/50">{item.label}</span>
            <strong className="text-paper">{formatPercent(item.value)}</strong>
          </div>
        ))}
      </div>
    </div>
  );
}
