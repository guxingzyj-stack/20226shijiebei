import { useEffect, useState } from "react";
import { Trophy } from "lucide-react";
import { apiGet } from "../api/client";
import type { LeaderboardEntry } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { formatMoney } from "../utils/format";

export function LeaderboardPage() {
  const { username } = useAuth();
  const [rows, setRows] = useState<LeaderboardEntry[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    apiGet<LeaderboardEntry[]>("/leaderboard").then(setRows).catch((err) => setError(err instanceof Error ? err.message : "排行榜加载失败"));
  }, []);

  return (
    <section className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold">虚拟资金排行榜</h1>
        <p className="mt-2 text-sm text-paper/60">仅展示模拟游戏余额，不代表真实收益。</p>
      </div>
      {error ? <div className="rounded-lg border border-danger/40 bg-danger/10 p-3 text-sm">{error}</div> : null}
      <div className="rounded-lg border border-white/10 bg-white/[0.06] p-3">
        {rows.map((row, index) => (
          <div key={`${row.username}-${index}`} className={`grid grid-cols-[48px_1fr_auto] items-center gap-3 rounded-lg px-3 py-3 ${row.username === username ? "bg-gold/15" : ""}`}>
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-pitch/70 text-gold">
              {index < 3 ? <Trophy size={18} /> : index + 1}
            </div>
            <div>
              <div className="font-semibold">{row.username}</div>
              <div className="text-xs text-paper/50">{row.settled_bets ?? 0} settled bets</div>
            </div>
            <div className="text-right font-semibold text-gold">{formatMoney(row.balance)}</div>
          </div>
        ))}
        {!rows.length ? <div className="p-4 text-sm text-paper/60">排行榜暂无数据。</div> : null}
      </div>
    </section>
  );
}
