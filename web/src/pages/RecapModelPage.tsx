import { type ReactNode, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { BarChart3, GitCompareArrows, Sigma } from "lucide-react";
import { apiGet } from "../api/client";
import type { MatchRecap, MatchRecapResponse, RecapRecentResponse, RecapSummary } from "../api/types";
import { InfoTip } from "../components/InfoTip";
import { MetricHelp } from "../components/MetricHelp";
import type { GlossaryKey } from "../recaps/glossary";
import { formatDateTime, formatPercent } from "../utils/format";
import { aggregateRecaps, outcomeText, predictionText, predictionTone } from "../recaps/recapUtils";

export function RecapModelPage() {
  const [recaps, setRecaps] = useState<MatchRecap[]>([]);
  const [summary, setSummary] = useState<RecapSummary | null>(null);
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
          setSummary(summaryResult);
          setRecaps(detailResults.flatMap((result) => (result.available && result.recap ? [result.recap] : [])));
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "模型表现加载失败");
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
  const hitRate =
    summary && summary.model_correct_count + summary.model_wrong_count > 0
      ? summary.model_correct_count / (summary.model_correct_count + summary.model_wrong_count)
      : null;

  return (
    <div className="space-y-4">
      <section className="rounded-lg border border-white/10 bg-white/[0.06] p-4 shadow-soft">
        <p className="text-sm font-medium text-gold">赛后复盘</p>
        <h1 className="mt-1 text-2xl font-semibold md:text-3xl">模型表现统计</h1>
        <p className="mt-3 max-w-3xl text-sm leading-6 text-paper/68">
          这里用已完赛且可复盘的比赛做只读统计。样本很小时只代表观察，不改变生产预测权重。
        </p>
      </section>

      {loading ? <div className="rounded-lg border border-white/10 p-5 text-paper/65">模型表现加载中</div> : null}
      {error ? <div className="rounded-lg border border-danger/40 bg-danger/10 p-4 text-sm">{error}</div> : null}

      {!loading && !error ? (
        <>
          <section className="grid gap-3 md:grid-cols-3 xl:grid-cols-6">
            <Metric label="已完赛" value={summary?.finished_matches ?? 0} />
            <Metric label="可复盘" value={summary?.recap_available_matches ?? 0} />
            <Metric label="模型命中" value={summary?.model_correct_count ?? 0} helpKey="modelHit" />
            <Metric label="模型未中" value={summary?.model_wrong_count ?? 0} helpText="模型赛前最看好的方向，与最终赛果不一致。" />
            <Metric label="缺预测" value={summary?.model_missing_count ?? 0} />
            <Metric label="命中率" value={hitRate === null ? "样本不足" : formatPercent(hitRate)} helpKey="hitRate" />
          </section>

          <section className="grid gap-3 lg:grid-cols-3">
            <Panel title="市场 vs 模型" icon={GitCompareArrows}>
              <Metric label="市场热门命中" value={aggregate.marketCorrectCount} />
              <Metric label="模型与市场同向" value={aggregate.modelMarketAgreeCount} />
              <Metric label="模型与市场分歧" value={aggregate.modelMarketDisagreeCount} />
            </Panel>
            <Panel title="样本状态" icon={Sigma}>
              <p className="text-sm leading-6 text-paper/65">
                当前可复盘样本 {recaps.length} 场。样本不足时继续观察，不把该统计用于生产权重调整。
              </p>
              <MetricHelp glossaryKey="sampleSmall" />
            </Panel>
            <Panel title="安全边界" icon={BarChart3}>
              <p className="text-sm leading-6 text-paper/65">P4 只读展示，不修改比分、注单、余额，也不改变 P1/P3 权重。</p>
            </Panel>
          </section>

          <section className="rounded-lg border border-white/10 bg-white/[0.055] p-4">
            <h2 className="text-lg font-semibold">最近比赛表现</h2>
            {recaps.length ? (
              <div className="mt-4 overflow-x-auto">
                <table className="w-full min-w-[820px] text-sm">
                  <thead className="text-left text-paper/45">
                    <tr>
                      <th className="py-2">比赛</th>
                      <th>时间</th>
                      <th>比分</th>
                      <th>市场方向</th>
                      <th>模型方向</th>
                      <th>实际结果</th>
                      <th>模型结果</th>
                    </tr>
                  </thead>
                  <tbody>
                    {recaps.map((recap) => (
                      <tr key={recap.match_id} className="border-t border-white/10">
                        <td className="py-2">
                          <Link to={`/recaps/${encodeURIComponent(recap.match_id)}`} className="text-paper hover:text-gold">
                            {recap.home_team} vs {recap.away_team}
                          </Link>
                        </td>
                        <td className="text-paper/60">{formatDateTime(recap.kickoff_at)}</td>
                        <td className="font-semibold text-gold">{recap.result.scoreline}</td>
                        <td>{outcomeText(recap.market.favorite)}</td>
                        <td>{outcomeText(recap.model.predicted_outcome)}</td>
                        <td>{outcomeText(recap.result.winner)}</td>
                        <td>
                          <span className={`rounded-full border px-3 py-1 text-xs ${predictionTone(recap.model.prediction_correct)}`}>
                            {predictionText(recap.model.prediction_correct)}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="mt-3 text-sm text-paper/60">样本不足，继续观察。</p>
            )}
          </section>
        </>
      ) : null}
    </div>
  );
}

function Panel({ title, icon: Icon, children }: { title: string; icon: typeof BarChart3; children: ReactNode }) {
  return (
    <section className="rounded-lg border border-white/10 bg-white/[0.055] p-4">
      <div className="mb-3 flex items-center gap-2 text-lg font-semibold">
        <Icon size={18} className="text-gold" />
        {title}
      </div>
      <div className="space-y-2">{children}</div>
    </section>
  );
}

function Metric({ label, value, helpKey, helpText }: { label: string; value: ReactNode; helpKey?: GlossaryKey; helpText?: string }) {
  return (
    <div className="rounded-lg border border-white/10 bg-pitch/62 px-3 py-2">
      <div className="text-xs text-paper/45">
        {label}
        <InfoTip glossaryKey={helpKey} text={helpText} label={label} />
      </div>
      <div className="mt-1 text-sm font-semibold text-paper">{value}</div>
    </div>
  );
}
