import { FormEvent, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { apiPost } from "../api/client";
import type { Bet } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { useBetSlip } from "../bet/BetSlipContext";
import { formatDecimal, formatMoney, playTypeLabel, selectionLabel } from "../utils/format";

const PARLAYS = ["single", "2x1", "3x1", "4x1", "5x1", "6x1", "7x1", "8x1"];

export function BetPage() {
  const { token, isAuthenticated } = useAuth();
  const { legs, removeLeg, clear } = useBetSlip();
  const [stake, setStake] = useState("10");
  const [parlay, setParlay] = useState("single");
  const [message, setMessage] = useState("");
  const [result, setResult] = useState<Bet | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const estimated = useMemo(() => {
    const product = legs.reduce((value, leg) => value * Number(leg.odds || 1), 1);
    return product * Number(stake || 0);
  }, [legs, stake]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!token) {
      setMessage("请先登录后进行虚拟下注。");
      return;
    }
    try {
      setSubmitting(true);
      setMessage("");
      const response = await apiPost<Bet>(
        "/bets",
        {
          legs: legs.map(({ match_id, play_type, selection }) => ({ match_id, play_type, selection })),
          parlay,
          stake: Number(stake),
        },
        token,
      );
      setResult(response);
      clear();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "虚拟下注提交失败");
    } finally {
      setSubmitting(false);
    }
  }

  if (!isAuthenticated) {
    return (
      <section className="rounded-lg border border-white/10 bg-white/[0.06] p-6">
        <h1 className="text-2xl font-semibold">模拟注单</h1>
        <p className="mt-3 text-paper/65">请先登录，系统会使用虚拟资金余额进行模拟下注。</p>
        <Link to="/auth" className="mt-5 inline-block rounded-lg bg-gold px-4 py-3 font-semibold text-pitch">
          登录 / 注册
        </Link>
      </section>
    );
  }

  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_360px]">
      <section className="rounded-lg border border-white/10 bg-white/[0.06] p-5">
        <h1 className="text-2xl font-semibold">虚拟下注台</h1>
        <p className="mt-2 text-sm text-paper/60">前端显示赔率仅供确认，最终以服务端最新赔率为准。</p>
        <div className="mt-5 space-y-3">
          {legs.length ? (
            legs.map((leg, index) => (
              <div key={`${leg.match_id}-${leg.play_type}-${leg.selection}`} className="rounded-lg border border-white/10 bg-pitch/70 p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="font-semibold">{leg.label || leg.match_id}</div>
                    <div className="mt-1 text-sm text-paper/58">
                      {playTypeLabel(leg.play_type)} · {selectionLabel(leg.selection)} · 显示赔率 {formatDecimal(leg.odds)}
                    </div>
                  </div>
                  <button type="button" onClick={() => removeLeg(index)} className="rounded border border-white/15 px-3 py-2 text-sm hover:bg-white/10">
                    移除
                  </button>
                </div>
              </div>
            ))
          ) : (
            <div className="rounded-lg border border-dashed border-white/18 p-5 text-sm text-paper/60">注单为空，请从比赛详情加入模拟选项。</div>
          )}
        </div>
      </section>

      <form onSubmit={submit} className="rounded-lg border border-white/10 bg-white/[0.06] p-5 shadow-soft">
        <h2 className="text-lg font-semibold">提交模拟注单</h2>
        <label className="mt-4 block text-sm text-paper/60">
          串关方式
          <select value={parlay} onChange={(event) => setParlay(event.target.value)} className="mt-2 w-full rounded-lg border border-white/10 bg-pitch px-3 py-3 text-paper">
            {PARLAYS.map((item) => (
              <option key={item} value={item}>{item}</option>
            ))}
          </select>
        </label>
        <label className="mt-4 block text-sm text-paper/60">
          虚拟 stake
          <input value={stake} onChange={(event) => setStake(event.target.value)} type="number" min="1" step="1" className="mt-2 w-full rounded-lg border border-white/10 bg-pitch px-3 py-3 text-paper" />
        </label>
        <div className="mt-4 rounded-lg bg-pitch/70 p-4">
          <div className="text-sm text-paper/55">潜在返还估算</div>
          <div className="mt-1 text-2xl font-semibold text-gold">{formatMoney(estimated)}</div>
        </div>
        <button disabled={!legs.length || submitting} className="mt-5 w-full rounded-lg bg-gold px-4 py-3 font-semibold text-pitch disabled:cursor-not-allowed disabled:opacity-50">
          {submitting ? "提交中" : "提交虚拟下注"}
        </button>
        {message ? <div className="mt-4 rounded-lg border border-danger/40 bg-danger/10 p-3 text-sm">{message}</div> : null}
        {result ? (
          <div className="mt-4 rounded-lg border border-gold/40 bg-gold/10 p-3 text-sm">
            <div>模拟注单 #{result.id} 已创建，状态 {result.status}</div>
            <div>服务端 potential_payout: {formatMoney(result.potential_payout)}</div>
            <div>当前虚拟余额: {formatMoney(result.balance)}</div>
          </div>
        ) : null}
      </form>
    </div>
  );
}
