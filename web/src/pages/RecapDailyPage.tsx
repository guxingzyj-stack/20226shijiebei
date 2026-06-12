import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ClipboardCopy, FileText, ShieldCheck } from "lucide-react";
import { apiGet } from "../api/client";
import type { MatchRecap, MatchRecapResponse, RecapRecentResponse } from "../api/types";
import { InfoTip } from "../components/InfoTip";
import { MetricHelp } from "../components/MetricHelp";
import { buildDailyReportText, groupRecapsByDay, outcomeText, predictionText } from "../recaps/recapUtils";

export function RecapDailyPage() {
  const [recaps, setRecaps] = useState<MatchRecap[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState("");

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
        if (!cancelled) setError(err instanceof Error ? err.message : "复盘日报加载失败");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, []);

  const groups = useMemo(() => groupRecapsByDay(recaps), [recaps]);

  async function copyReport(dateKey: string, text: string) {
    await navigator.clipboard.writeText(text);
    setCopied(dateKey);
    window.setTimeout(() => setCopied(""), 1600);
  }

  return (
    <div className="space-y-4">
      <section className="rounded-lg border border-white/10 bg-white/[0.06] p-4 shadow-soft">
        <p className="text-sm font-medium text-gold">赛后复盘</p>
        <h1 className="mt-1 text-2xl font-semibold md:text-3xl">复盘日报</h1>
        <p className="mt-3 max-w-3xl text-sm leading-6 text-paper/68">
          按比赛日汇总赛果、模型命中、市场判断、EV 观察和结算状态，可复制为日报文案。
        </p>
      </section>

      <MetricHelp title="这是什么？">
        复盘日报把同一比赛日的赛果、模型命中、市场热门、EV 研究信号和结算状态整理成只读摘要，方便赛后回看。
      </MetricHelp>

      {loading ? <div className="rounded-lg border border-white/10 p-5 text-paper/65">复盘日报加载中</div> : null}
      {error ? <div className="rounded-lg border border-danger/40 bg-danger/10 p-4 text-sm">{error}</div> : null}

      {!loading && !error && groups.length === 0 ? (
        <section className="rounded-lg border border-white/10 bg-white/[0.05] p-6 text-sm text-paper/65">
          暂无已完赛复盘日报，比赛结束后自动生成。
        </section>
      ) : null}

      {!loading && !error && groups.length ? (
        <div className="space-y-4">
          {groups.map((group) => {
            const reportText = buildDailyReportText(group);
            return (
              <section key={group.dateKey} className="rounded-lg border border-white/10 bg-white/[0.055] p-4">
                <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                  <div>
                    <div className="flex items-center gap-2 text-lg font-semibold">
                      <FileText size={18} className="text-gold" />
                      {group.dateKey}
                    </div>
                    <p className="mt-2 text-sm text-paper/60">
                      完赛 {group.recaps.length} 场，模型命中 {group.recaps.filter((recap) => recap.model.prediction_correct === true).length} 场，
                      市场热门命中 {group.aggregate.marketCorrectCount} 场。
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => copyReport(group.dateKey, reportText)}
                    className="inline-flex items-center justify-center gap-2 rounded-lg border border-gold/45 px-3 py-2 text-sm text-gold transition hover:bg-gold/10"
                  >
                    <ClipboardCopy size={16} />
                    {copied === group.dateKey ? "已复制" : "复制日报文案"}
                  </button>
                </div>

                <div className="mt-3 grid gap-3 md:grid-cols-2">
                  {group.recaps.map((recap) => (
                    <Link
                      key={recap.match_id}
                      to={`/recaps/${encodeURIComponent(recap.match_id)}`}
                      className="rounded-lg border border-white/10 bg-pitch/58 p-4 transition hover:border-gold/50"
                    >
                      <div className="text-xs text-paper/50">{recap.match_num || recap.match_id}</div>
                      <div className="mt-1 text-base font-semibold">
                        {recap.home_team} <span className="text-gold">{recap.result.scoreline}</span> {recap.away_team}
                      </div>
                      <div className="mt-3 grid gap-2 text-sm text-paper/65">
                        <span>
                          模型
                          <InfoTip glossaryKey="modelHit" />：{predictionText(recap.model.prediction_correct)}，方向 {outcomeText(recap.model.predicted_outcome)}
                        </span>
                        <span>
                          市场热门
                          <InfoTip glossaryKey="marketFavorite" />：{outcomeText(recap.market.favorite)}
                        </span>
                        <span>
                          EV
                          <InfoTip glossaryKey="evSignal" />：{recap.ev.total_ev_signals} 条研究/观察信号
                        </span>
                        <span>
                          结算
                          <InfoTip glossaryKey="noPublicBets" />：
                          {recap.settlement.settlement_status === "no_public_bets" ? "暂无公开注单结算" : recap.settlement.settlement_status}
                        </span>
                      </div>
                    </Link>
                  ))}
                </div>

                <div className="mt-3 rounded-lg border border-white/10 bg-pitch/68 p-3">
                  <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-paper">
                    <ShieldCheck size={16} className="text-gold" />
                    日报文案预览
                  </div>
                  <pre className="max-h-48 overflow-y-auto whitespace-pre-wrap text-xs leading-5 text-paper/68">{reportText}</pre>
                </div>
              </section>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
