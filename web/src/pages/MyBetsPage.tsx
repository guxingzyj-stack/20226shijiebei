import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiGet } from "../api/client";
import type { Bet } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { formatDateTime, formatMoney, playTypeLabel, selectionLabel } from "../utils/format";

export function MyBetsPage() {
  const { token, isAuthenticated } = useAuth();
  const [bets, setBets] = useState<Bet[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!token) return;
    apiGet<Bet[]>("/bets/me", token).then(setBets).catch((err) => setError(err instanceof Error ? err.message : "注单加载失败"));
  }, [token]);

  if (!isAuthenticated) {
    return (
      <section className="rounded-lg border border-white/10 bg-white/[0.06] p-6">
        <h1 className="text-2xl font-semibold">我的模拟注单</h1>
        <p className="mt-3 text-paper/65">登录后查看虚拟下注记录。</p>
        <Link to="/auth" className="mt-5 inline-block rounded-lg bg-gold px-4 py-3 font-semibold text-pitch">登录 / 注册</Link>
      </section>
    );
  }

  return (
    <section className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold">我的模拟注单</h1>
        <p className="mt-2 text-sm text-paper/60">open / won / lost / void 状态仅用于虚拟资金结算。</p>
      </div>
      {error ? <div className="rounded-lg border border-danger/40 bg-danger/10 p-3 text-sm">{error}</div> : null}
      {bets.map((bet) => (
        <article key={bet.id} className="rounded-lg border border-white/10 bg-white/[0.06] p-4">
          <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
            <div>
              <div className="font-semibold">模拟注单 #{bet.id}</div>
              <div className="text-sm text-paper/55">{bet.placed_at ? formatDateTime(bet.placed_at) : "-"} · {bet.parlay}</div>
            </div>
            <span className="w-fit rounded-full border border-white/15 px-3 py-1 text-sm text-paper/75">{bet.status}</span>
          </div>
          <div className="mt-4 space-y-2">
            {bet.legs.map((leg, index) => (
              <div key={`${bet.id}-${index}`} className="rounded-lg bg-pitch/65 px-3 py-2 text-sm">
                {leg.match_id} · {playTypeLabel(leg.play_type)} · {selectionLabel(leg.selection)} · odds {leg.odds}
              </div>
            ))}
          </div>
          <div className="mt-4 grid gap-2 text-sm text-paper/70 md:grid-cols-4">
            <div>stake: {formatMoney(bet.stake)}</div>
            <div>potential: {formatMoney(bet.potential_payout)}</div>
            <div>payout: {formatMoney(bet.payout)}</div>
            <div>settled: {bet.settled_at ? formatDateTime(bet.settled_at) : "-"}</div>
          </div>
        </article>
      ))}
      {!bets.length ? <div className="rounded-lg border border-white/10 p-5 text-sm text-paper/60">暂无模拟注单。</div> : null}
    </section>
  );
}
