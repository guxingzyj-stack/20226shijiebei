import { type ReactNode, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, BarChart3, ShieldCheck } from "lucide-react";
import { apiGet } from "../api/client";
import type { MatchRecap, MatchRecapResponse, RecapRecentResponse } from "../api/types";
import { InfoTip } from "../components/InfoTip";
import { MetricHelp } from "../components/MetricHelp";
import type { GlossaryKey } from "../recaps/glossary";
import { formatDecimal, formatPercent, playTypeLabel, selectionLabel } from "../utils/format";
import { type AggregatedEvSignal, aggregateEvSignals, aggregateRecaps, evResultText } from "../recaps/recapUtils";

type EvRow = MatchRecap["ev"]["signals"][number] & {
  match_id: string;
  match_label: string;
  scoreline: string;
};

export function RecapEvPage() {
  const [recaps, setRecaps] = useState<MatchRecap[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        setLoading(true);
        const recentResult = await apiGet<RecapRecentResponse>("/recaps/recent?limit=20");
        const detailResults = await Promise.all(
          recentResult.items.map((item) => apiGet<MatchRecapResponse>(`/recaps/matches/${encodeURIComponent(item.match_id)}`)),
        );
        if (!cancelled) {
          setRecaps(detailResults.flatMap((result) => (result.available && result.recap ? [result.recap] : [])));
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "EV 表现加载失败");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, []);

  const aggregate = useMemo(() => aggregateRecaps(recaps), [recaps]);
  const rows = useMemo<AggregatedEvSignal<EvRow>[]>(
    () =>
      aggregateEvSignals(
        recaps.flatMap((recap) =>
          recap.ev.signals.map((signal) => ({
            ...signal,
            match_id: recap.match_id,
            match_label: `${recap.home_team} vs ${recap.away_team}`,
            scoreline: recap.result.scoreline,
          })),
        )
      ),
    [recaps],
  );
  const visibleRows = expanded ? rows : rows.slice(0, 20);

  return (
    <div className="space-y-5">
      <section className="rounded-lg border border-white/10 bg-white/[0.06] p-5 shadow-soft">
        <p className="text-sm font-medium text-gold">赛后复盘</p>
        <h1 className="mt-1 text-2xl font-semibold md:text-3xl">EV 信号表现</h1>
        <p className="mt-3 max-w-3xl text-sm leading-6 text-paper/68">
          EV 信号用于赛后研究与模型复盘，不构成投注建议。当前 BETTING_ENABLED=false。
        </p>
      </section>

      {loading ? <div className="rounded-lg border border-white/10 p-5 text-paper/65">EV 表现加载中</div> : null}
      {error ? <div className="rounded-lg border border-danger/40 bg-danger/10 p-4 text-sm">{error}</div> : null}

      {!loading && !error ? (
        <>
          <section className="grid gap-3 md:grid-cols-3 xl:grid-cols-6">
            <Metric label="EV 信号总数" value={aggregate.totalEvSignals} helpKey="evSignal" />
            <Metric label="高 EV 信号" value={aggregate.highEvCount} helpKey="highEv" />
            <Metric label="研究信号" value={aggregate.researchOnlyCount} helpKey="researchOnly" />
            <Metric label="候选信号" value={aggregate.suggestionEligibleCount} helpKey="suggestionEligible" />
            <Metric label="命中" value={aggregate.evHitCount} />
            <Metric label="复盘未命中" value={aggregate.evMissCount} helpKey="evMiss" />
          </section>

          <section className="grid gap-4 lg:grid-cols-2">
            <Panel title="安全说明" icon={ShieldCheck}>
              <p className="text-sm leading-6 text-paper/65">
                research_only 只显示为“研究信号”。页面不提供真实购彩入口，也不根据 EV 生成投注建议。
              </p>
              <MetricHelp glossaryKey="evSignal" />
            </Panel>
            <Panel title="样本状态" icon={AlertTriangle}>
              <p className="text-sm leading-6 text-paper/65">
                当前聚合 {recaps.length} 场已完赛复盘。样本较少时，EV 命中/未中只用于观察。
              </p>
              <MetricHelp glossaryKey="sampleSmall" />
            </Panel>
          </section>

          <section className="rounded-lg border border-white/10 bg-white/[0.055] p-5">
            <div className="flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
              <div>
                <h2 className="text-lg font-semibold">EV 信号列表</h2>
                <p className="mt-1 text-xs text-paper/50">默认展示 Top 20，按 EV 从高到低排序，并聚合重复信号。</p>
              </div>
              {rows.length > 20 ? (
                <button
                  type="button"
                  onClick={() => setExpanded((value) => !value)}
                  className="inline-flex items-center justify-center rounded-lg border border-gold/45 px-3 py-2 text-sm text-gold transition hover:bg-gold/10"
                >
                  {expanded ? "收起" : `展开全部 ${rows.length} 条聚合信号`}
                </button>
              ) : null}
            </div>
            {rows.length ? (
              <div className="mt-4 overflow-x-auto">
                <table className="w-full min-w-[900px] text-sm">
                  <thead className="text-left text-paper/45">
                    <tr>
                      <th className="py-2">比赛</th>
                      <th>比分</th>
                      <th>玩法</th>
                      <th>选项</th>
                      <th>模型概率</th>
                      <th>赔率</th>
                      <th>
                        EV
                        <InfoTip glossaryKey="ev" />
                      </th>
                      <th>出现次数</th>
                      <th>标记</th>
                      <th>结果</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visibleRows.map((signal, index) => (
                      <tr key={`${signal.match_id}-${signal.play_type}-${signal.selection}-${signal.model_version}-${index}`} className="border-t border-white/10">
                        <td className="py-2">
                          <Link to={`/recaps/${encodeURIComponent(signal.match_id)}`} className="text-paper hover:text-gold">
                            {signal.match_label}
                          </Link>
                        </td>
                        <td className="text-gold">{signal.scoreline}</td>
                        <td>{playTypeLabel(signal.play_type)}</td>
                        <td>{selectionLabel(signal.selection)}</td>
                        <td>{formatPercent(signal.model_prob)}</td>
                        <td>{formatDecimal(signal.odds)}</td>
                        <td className={Number(signal.ev || 0) > 0 ? "text-gold" : "text-paper/65"}>{formatDecimal(signal.ev, 3)}</td>
                        <td>{signal.occurrence_count > 1 ? `出现次数 x ${signal.occurrence_count}` : "1"}</td>
                        <td>{signal.research_only ? "研究信号" : signal.suggestion_eligible ? "候选信号" : "观察信号"}</td>
                        <td>{evResultText(signal.hit)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="mt-3 text-sm text-paper/60">暂无 EV 信号，比赛完赛后继续观察。</p>
            )}
          </section>
        </>
      ) : null}
    </div>
  );
}

function Panel({ title, icon: Icon, children }: { title: string; icon: typeof BarChart3; children: ReactNode }) {
  return (
    <section className="rounded-lg border border-white/10 bg-white/[0.055] p-5">
      <div className="mb-4 flex items-center gap-2 text-lg font-semibold">
        <Icon size={18} className="text-gold" />
        {title}
      </div>
      {children}
    </section>
  );
}

function Metric({ label, value, helpKey }: { label: string; value: ReactNode; helpKey?: GlossaryKey }) {
  return (
    <div className="rounded-lg border border-white/10 bg-pitch/62 px-3 py-2">
      <div className="text-xs text-paper/45">
        {label}
        <InfoTip glossaryKey={helpKey} label={label} />
      </div>
      <div className="mt-1 text-sm font-semibold text-paper">{value}</div>
    </div>
  );
}
