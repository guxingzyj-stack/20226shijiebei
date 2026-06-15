import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, BarChart3, CheckCircle2, Clock3, FileText, Radar, ShieldCheck } from "lucide-react";
import { apiGet } from "../api/client";
import type { MatchRecap, MatchRecapResponse, RecapRecentResponse, RecapSummary } from "../api/types";
import { InfoTip } from "../components/InfoTip";
import { MetricHelp } from "../components/MetricHelp";
import { formatDateTime, formatMoney } from "../utils/format";
import { outcomeText, predictionText, predictionTone, settlementText } from "../recaps/recapUtils";

export function RecapsPage() {
  const [recent, setRecent] = useState<RecapRecentResponse | null>(null);
  const [summary, setSummary] = useState<RecapSummary | null>(null);
  const [recaps, setRecaps] = useState<MatchRecap[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        setLoading(true);
        const [recentResult, summaryResult] = await Promise.all([
          apiGet<RecapRecentResponse>("/recaps/recent?limit=20"),
          apiGet<RecapSummary>("/recaps/summary"),
        ]);
        const detailResults = await Promise.all(
          recentResult.items.map((item) => apiGet<MatchRecapResponse>(`/recaps/matches/${encodeURIComponent(item.match_id)}`)),
        );
        if (!cancelled) {
          setRecent(recentResult);
          setSummary(summaryResult);
          setRecaps(detailResults.flatMap((result) => (result.available && result.recap ? [result.recap] : [])));
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "复盘数据加载失败");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, []);

  const items = recent?.items || [];
  const recapById = new Map(recaps.map((recap) => [recap.match_id, recap]));
  const vig = summary?.cumulative_vig;

  return (
    <div className="space-y-5">
      <section className="rounded-lg border border-white/10 bg-white/[0.06] p-5 shadow-soft">
        <p className="text-sm font-medium text-gold">赛后复盘</p>
        <div className="mt-1 flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
          <div>
            <h1 className="text-2xl font-semibold md:text-3xl">复盘报告</h1>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-paper/68">
              每场完赛后自动汇总赛果、市场赔率、模型方向、EV 研究信号与结算状态。这里只展示只读复盘，不提供真实购彩服务。
            </p>
          </div>
          <div className="grid grid-cols-2 gap-2 text-sm md:grid-cols-4">
            <Stat label="已完赛" value={summary?.finished_matches ?? 0} helpText="已有正式赛果的比赛数。" />
            <Stat label="可复盘" value={summary?.recap_available_matches ?? 0} helpText="赛果、赔率或预测数据足够生成复盘的比赛。" />
            <Stat label="模型命中" value={summary?.model_correct_count ?? 0} helpKey="modelHit" />
            <Stat label="EV 信号" value={summary?.ev_signal_count ?? 0} helpKey="evSignal" />
          </div>
        </div>
      </section>

      <MetricHelp title="这是什么？">
        复盘报告只读展示已完赛比赛的赛果、市场方向、模型判断和 EV 研究信号。样本少时只能观察趋势，不适合下长期结论。
      </MetricHelp>

      <section className="rounded-lg border border-gold/25 bg-gold/10 p-5">
        <h2 className="text-lg font-semibold text-paper">累计被抽水</h2>
        <p className="mt-3 text-sm leading-6 text-paper/72">
          {vig && vig.bet_count > 0
            ? `这一届你（虚拟）下注 ${vig.bet_count} 笔共 ${formatMoney(vig.total_virtual_stake)} 点，如果是真钱，大约 ${formatMoney(vig.cumulative_vig_points)} 点进了庄家口袋。还好是假的 😃`
            : "暂无虚拟下注记录。等投注模拟开放后，这里会显示你被“庄家抽水”的累计成本。"}
        </p>
        <div className="mt-3 text-xs text-paper/55">资金曲线后续会叠加“累计被抽水”线；当前仅做只读复盘，不开放真实购彩。</div>
      </section>

      <section className="grid gap-3 md:grid-cols-3">
        <QuickLink to="/recaps/model" icon={Radar} title="模型表现" text="查看模型命中、市场分歧和样本状态" />
        <QuickLink to="/recaps/ev" icon={BarChart3} title="EV 信号" text="复盘研究信号命中与风险标记" />
        <QuickLink to="/recaps/daily" icon={FileText} title="复盘日报" text="按比赛日生成可复制日报文案" />
      </section>

      {loading ? <div className="rounded-lg border border-white/10 p-5 text-paper/65">复盘列表加载中</div> : null}
      {error ? <div className="rounded-lg border border-danger/40 bg-danger/10 p-4 text-sm">{error}</div> : null}

      {!loading && !error && items.length === 0 ? (
        <section className="rounded-lg border border-white/10 bg-white/[0.05] p-6 text-sm text-paper/65">
          暂无已完赛复盘，比赛结束后自动生成。
        </section>
      ) : null}

      {items.length ? (
        <section className="grid gap-3 lg:grid-cols-2">
          {items.map((item) => {
            const recap = recapById.get(item.match_id);
            return (
              <Link
                key={item.match_id}
                to={`/recaps/${encodeURIComponent(item.match_id)}`}
                className="rounded-lg border border-white/10 bg-white/[0.055] p-4 transition hover:border-gold/55 hover:bg-white/[0.08]"
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="text-xs text-paper/50">{item.match_num || item.match_id}</div>
                    <div className="mt-2 text-lg font-semibold">
                      {item.home_team} <span className="text-paper/35">vs</span> {item.away_team}
                    </div>
                    <div className="mt-1 text-xs text-paper/45">{recap ? formatDateTime(recap.kickoff_at) : "时间读取中"}</div>
                  </div>
                  <ArrowRight className="shrink-0 text-paper/45" size={20} />
                </div>
                <div className="mt-4 flex flex-wrap items-center gap-2">
                  <span className="rounded-md bg-pitch/75 px-3 py-1 text-xl font-semibold text-gold">{item.scoreline}</span>
                  <span className={`rounded-full border px-3 py-1 text-xs ${predictionTone(item.prediction_correct)}`}>
                    模型{predictionText(item.prediction_correct)}
                  </span>
                  <span className="rounded-full border border-white/12 px-3 py-1 text-xs text-paper/60">查看复盘</span>
                </div>
                <div className="mt-3 grid gap-2 text-sm text-paper/62 md:grid-cols-2">
                  <span>市场方向：{recap ? outcomeText(recap.market.favorite) : "读取中"}</span>
                  <span>模型方向：{recap ? outcomeText(recap.model.predicted_outcome) : "读取中"}</span>
                  <span>EV 信号：{recap ? recap.ev.total_ev_signals : 0}</span>
                  <span>结算：{recap ? settlementText(recap.settlement.settlement_status) : "读取中"}</span>
                </div>
                <p className="mt-3 text-sm leading-6 text-paper/62">{item.title}</p>
              </Link>
            );
          })}
        </section>
      ) : null}
    </div>
  );
}

function QuickLink({ to, icon: Icon, title, text }: { to: string; icon: typeof BarChart3; title: string; text: string }) {
  return (
    <Link to={to} className="rounded-lg border border-white/10 bg-white/[0.05] p-4 transition hover:border-gold/50 hover:bg-white/[0.075]">
      <div className="flex items-center gap-2 font-semibold">
        <Icon size={18} className="text-gold" />
        {title}
      </div>
      <p className="mt-2 text-sm leading-5 text-paper/58">{text}</p>
    </Link>
  );
}

function Stat({ label, value, helpKey, helpText }: { label: string; value: number; helpKey?: Parameters<typeof InfoTip>[0]["glossaryKey"]; helpText?: string }) {
  return (
    <div className="rounded-lg border border-white/10 bg-pitch/65 px-3 py-2">
      <div className="flex items-center gap-1 text-xs text-paper/50">
        {label === "已完赛" ? <Clock3 size={13} /> : null}
        {label === "可复盘" ? <ShieldCheck size={13} /> : null}
        {label === "模型命中" ? <CheckCircle2 size={13} /> : null}
        {label === "EV 信号" ? <BarChart3 size={13} /> : null}
        {label}
        <InfoTip glossaryKey={helpKey} text={helpText} label={label} />
      </div>
      <div className="mt-1 text-lg font-semibold text-paper">{value}</div>
    </div>
  );
}
