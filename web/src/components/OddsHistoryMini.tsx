import type { OddsSnapshot } from "../api/types";
import { formatDateTime, formatDecimal } from "../utils/format";

export function OddsHistoryMini({ rows }: { rows: OddsSnapshot[] }) {
  if (!rows.length) {
    return <div className="text-sm text-paper/60">暂无赔率历史</div>;
  }
  const latest = rows.slice(-6);
  return (
    <div className="space-y-2">
      {latest.map((row) => (
        <div key={row.id} className="grid grid-cols-[1fr_auto] items-center gap-3 rounded-lg bg-white/5 px-3 py-2 text-sm">
          <span className="text-paper/65">{formatDateTime(row.fetched_at)}</span>
          <span className="font-mono text-paper">
            {["3", "1", "0"].map((key) => formatDecimal(row.odds[key])).join(" / ")}
          </span>
        </div>
      ))}
    </div>
  );
}
