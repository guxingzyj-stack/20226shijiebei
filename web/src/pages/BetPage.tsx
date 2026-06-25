import { FormEvent, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { CheckCircle2, Loader2, RefreshCw, SendHorizontal, Sparkles, Trash2 } from "lucide-react";
import { apiGet, apiPost } from "../api/client";
import type { Bet, BetPlanItem, BetPlanResponse, BetPlanSubmitResponse } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { useBetSlip } from "../bet/BetSlipContext";
import { formatDateTime, formatDecimal, formatMoney, formatPercent, playTypeLabel, selectionLabel } from "../utils/format";

const PARLAYS = ["single", "2x1", "3x1", "4x1", "5x1", "6x1", "7x1", "8x1"];
const BETTING_ENABLED = import.meta.env.VITE_BETTING_ENABLED === "true";
const BETTING_DISABLED_COPY = "模拟投注即将开放，结算系统验收通过后开启。当前可查看预测、赔率走势和 EV 信号。";

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
    if (!BETTING_ENABLED) {
      setMessage(BETTING_DISABLED_COPY);
      return;
    }
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
        <p className="mt-3 text-paper/65">请先登录，系统会使用虚拟资金余额生成数据方案或提交手动下注。</p>
        <Link to="/auth" className="mt-5 inline-block rounded-lg bg-gold px-4 py-3 font-semibold text-pitch">
          登录 / 注册
        </Link>
      </section>
    );
  }

  return (
    <div className="space-y-5">
      <DataBetPlanCard token={token} />

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_360px]">
        <section className="rounded-lg border border-white/10 bg-white/[0.06] p-5">
          <h1 className="text-2xl font-semibold">手动下注单</h1>
          <p className="mt-2 text-sm text-paper/60">前端显示赔率仅供确认，最终以服务端最新赔率为准。</p>
          <div className="mt-5 space-y-3">
            {legs.length ? (
              legs.map((leg, index) => (
                <div key={`${leg.match_id}-${leg.play_type}-${leg.selection}`} className="rounded-lg border border-white/10 bg-pitch/70 p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="font-semibold">{leg.label || leg.match_id}</div>
                      <div className="mt-1 text-sm text-paper/58">
                        {playTypeLabel(leg.play_type)} / {selectionLabel(leg.selection)} / 显示赔率 {formatDecimal(leg.odds)}
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => removeLeg(index)}
                      className="inline-flex h-9 w-9 items-center justify-center rounded border border-white/15 hover:bg-white/10"
                      title="移除"
                    >
                      <Trash2 size={16} />
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
          {!BETTING_ENABLED ? (
            <div className="mt-4 rounded-lg border border-gold/35 bg-gold/10 p-3 text-sm text-gold">{BETTING_DISABLED_COPY}</div>
          ) : null}
          <label className="mt-4 block text-sm text-paper/60">
            串关方式
            <select value={parlay} onChange={(event) => setParlay(event.target.value)} className="mt-2 w-full rounded-lg border border-white/10 bg-pitch px-3 py-3 text-paper">
              {PARLAYS.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
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
          <button disabled={!BETTING_ENABLED || !legs.length || submitting} className="mt-5 inline-flex w-full items-center justify-center gap-2 rounded-lg bg-gold px-4 py-3 font-semibold text-pitch disabled:cursor-not-allowed disabled:opacity-50">
            {submitting ? <Loader2 size={18} className="animate-spin" /> : <SendHorizontal size={18} />}
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
    </div>
  );
}

function DataBetPlanCard({ token }: { token: string | null }) {
  const [budget, setBudget] = useState("100");
  const [maxBets, setMaxBets] = useState<3 | 5 | 8>(5);
  const [plan, setPlan] = useState<BetPlanResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState<BetPlanSubmitResponse | null>(null);

  useEffect(() => {
    if (token) {
      void loadPlan();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const budgetValue = Number(budget || 0);
  const canSubmit = BETTING_ENABLED && Boolean(plan?.available) && !loading && !submitting;

  async function loadPlan() {
    if (!token) return;
    try {
      setLoading(true);
      setError("");
      setSuccess(null);
      const params = new URLSearchParams({
        budget: String(Number.isFinite(budgetValue) && budgetValue > 0 ? budgetValue : 100),
        max_bets: String(maxBets),
      });
      const response = await apiGet<BetPlanResponse>(`/model/bet-plan?${params.toString()}`, token);
      setPlan(response);
    } catch (err) {
      setPlan(null);
      setError(err instanceof Error ? err.message : "数据方案生成失败");
    } finally {
      setLoading(false);
    }
  }

  async function submitPlan() {
    if (!token) return;
    if (!BETTING_ENABLED) {
      setError(BETTING_DISABLED_COPY);
      return;
    }
    try {
      setSubmitting(true);
      setError("");
      const response = await apiPost<BetPlanSubmitResponse>(
        "/bets/plan",
        {
          budget: Number.isFinite(budgetValue) && budgetValue > 0 ? budgetValue : 100,
          max_bets: maxBets,
        },
        token,
      );
      setPlan(response.plan_snapshot);
      setSuccess(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : "一键提交方案失败");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="rounded-lg border border-gold/25 bg-white/[0.06] p-5 shadow-soft">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="inline-flex items-center gap-2 text-sm font-medium text-gold">
            <Sparkles size={16} />
            数据方案
          </div>
          <h1 className="mt-2 text-2xl font-semibold">一键生成多笔单关</h1>
          <p className="mt-2 text-sm text-paper/60">按当前 EV、赔率和余额生成最多 8 笔虚拟单关，提交前服务端会重新计算。</p>
        </div>
        {!BETTING_ENABLED ? <div className="rounded-lg border border-gold/35 bg-gold/10 px-3 py-2 text-sm text-gold">{BETTING_DISABLED_COPY}</div> : null}
      </div>

      <div className="mt-5 grid gap-3 lg:grid-cols-[180px_220px_auto] lg:items-end">
        <label className="block text-sm text-paper/60">
          总预算
          <input value={budget} onChange={(event) => setBudget(event.target.value)} type="number" min="1" step="1" className="mt-2 w-full rounded-lg border border-white/10 bg-pitch px-3 py-3 text-paper" />
        </label>
        <div>
          <div className="text-sm text-paper/60">最大笔数</div>
          <div className="mt-2 grid grid-cols-3 overflow-hidden rounded-lg border border-white/10">
            {([3, 5, 8] as const).map((value) => (
              <button
                key={value}
                type="button"
                onClick={() => setMaxBets(value)}
                className={`px-3 py-3 text-sm font-semibold ${maxBets === value ? "bg-gold text-pitch" : "bg-pitch text-paper/70 hover:bg-white/10"}`}
              >
                {value}
              </button>
            ))}
          </div>
        </div>
        <div className="flex flex-col gap-2 sm:flex-row lg:justify-end">
          <button type="button" onClick={loadPlan} disabled={loading} className="inline-flex items-center justify-center gap-2 rounded-lg border border-white/12 px-4 py-3 text-sm font-semibold hover:bg-white/10 disabled:opacity-50">
            {loading ? <Loader2 size={17} className="animate-spin" /> : <RefreshCw size={17} />}
            生成方案
          </button>
          <button type="button" onClick={submitPlan} disabled={!canSubmit} className="inline-flex items-center justify-center gap-2 rounded-lg bg-gold px-4 py-3 text-sm font-semibold text-pitch disabled:cursor-not-allowed disabled:opacity-50">
            {submitting ? <Loader2 size={17} className="animate-spin" /> : <SendHorizontal size={17} />}
            一键提交方案
          </button>
        </div>
      </div>

      <PlanStatus plan={plan} loading={loading} error={error} success={success} />
    </section>
  );
}

function PlanStatus({
  plan,
  loading,
  error,
  success,
}: {
  plan: BetPlanResponse | null;
  loading: boolean;
  error: string;
  success: BetPlanSubmitResponse | null;
}) {
  if (loading && !plan) {
    return <div className="mt-5 rounded-lg border border-white/10 p-4 text-sm text-paper/60">正在读取最新赔率和 EV 信号...</div>;
  }
  return (
    <div className="mt-5 space-y-4">
      {error ? <div className="rounded-lg border border-danger/40 bg-danger/10 p-3 text-sm">{error}</div> : null}
      {success ? (
        <div className="rounded-lg border border-gold/40 bg-gold/10 p-4 text-sm">
          <div className="flex items-center gap-2 font-semibold text-gold">
            <CheckCircle2 size={17} />
            已创建 {success.created_bets.length} 笔单关
          </div>
          <div className="mt-2 text-paper/70">注单 ID：{success.created_bets.map((bet) => `#${bet.id}`).join("、")}</div>
          <div className="mt-1 text-paper/70">提交后余额：{formatMoney(success.balance_after)}</div>
        </div>
      ) : null}
      {plan ? (
        <>
          <div className="grid gap-3 text-sm sm:grid-cols-3">
            <PlanMetric label="预算上限" value={formatMoney(plan.total_budget)} />
            <PlanMetric label="计划投入" value={formatMoney(plan.total_stake)} />
            <PlanMetric label="计划笔数" value={`${plan.items.length}`} />
          </div>
          {plan.warnings.length ? <div className="rounded-lg border border-gold/35 bg-gold/10 p-3 text-sm text-gold">{plan.warnings.join(" / ")}</div> : null}
          {!plan.available ? (
            <div className="rounded-lg border border-white/10 bg-pitch/70 p-4 text-sm text-paper/60">
              暂无可提交的数据方案{plan.blockers.length ? `：${plan.blockers.join(" / ")}` : ""}
            </div>
          ) : (
            <div className="grid gap-3 xl:grid-cols-2">
              {plan.items.map((item) => (
                <PlanItemCard key={`${item.match_id}-${item.play_type}-${item.selection}`} item={item} />
              ))}
            </div>
          )}
        </>
      ) : null}
    </div>
  );
}

function PlanItemCard({ item }: { item: BetPlanItem }) {
  return (
    <div className="rounded-lg border border-white/10 bg-pitch/70 p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate font-semibold">
            {item.home_team} <span className="text-paper/35">vs</span> {item.away_team}
          </div>
          <div className="mt-1 text-xs text-paper/50">{item.kickoff_at ? formatDateTime(item.kickoff_at) : item.match_id}</div>
        </div>
        <div className="shrink-0 rounded border border-gold/35 px-2 py-1 text-xs font-semibold text-gold">单关</div>
      </div>
      <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
        <PlanMetric label="玩法" value={playTypeLabel(item.play_type)} />
        <PlanMetric label="选项" value={item.selection_label || selectionLabel(item.selection)} />
        <PlanMetric label="当前赔率" value={formatDecimal(item.odds)} />
        <PlanMetric label="EV" value={formatPercent(item.ev)} />
        <PlanMetric label="建议 stake" value={formatMoney(item.stake)} />
        <PlanMetric label="潜在返还" value={formatMoney(item.potential_payout)} />
      </div>
    </div>
  );
}

function PlanMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-white/10 bg-black/10 px-3 py-2">
      <div className="text-xs text-paper/50">{label}</div>
      <div className="mt-1 font-semibold text-paper">{value}</div>
    </div>
  );
}
