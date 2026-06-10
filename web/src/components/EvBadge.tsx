import { formatDecimal, toNumber } from "../utils/format";

export function EvBadge({ ev }: { ev?: string | number | null }) {
  const value = toNumber(ev);
  const tone =
    value > 0 ? "border-gold/60 bg-gold/15 text-gold" : value > -0.02 ? "border-yellow-300/50 bg-yellow-300/10 text-yellow-100" : "border-white/15 bg-white/5 text-paper/60";
  const label = value > 0 ? `EV +${formatDecimal(value)}` : value > -0.02 ? "接近打平" : "暂无价值信号";
  return <span className={`rounded-full border px-2.5 py-1 text-xs font-semibold ${tone}`}>{label}</span>;
}
