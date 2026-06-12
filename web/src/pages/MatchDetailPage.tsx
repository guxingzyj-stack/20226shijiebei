import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import { PlusCircle } from "lucide-react";
import { apiGet } from "../api/client";
import type { EvSignal, Match, OddsSnapshot, PredictionHistoryResponse, Suggestion, TeamFormResponse } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { useBetSlip } from "../bet/BetSlipContext";
import { BetSlipCompact } from "../components/BetSlip";
import { EvBadge } from "../components/EvBadge";
import { InfoTip } from "../components/InfoTip";
import { MarketModelCompare } from "../components/MarketModelCompare";
import { MetricHelp } from "../components/MetricHelp";
import { OddsHistoryMini } from "../components/OddsHistoryMini";
import { OddsTrendMini } from "../components/OddsTrendMini";
import { PredictionDriftMini } from "../components/PredictionDriftMini";
import { ProbabilityBar } from "../components/ProbabilityBar";
import { ScoreMatrix } from "../components/ScoreMatrix";
import { ScoreMatrixSummaryCard } from "../components/ScoreMatrixSummaryCard";
import { TeamFormMini } from "../components/TeamFormMini";
import { formatDateTime, formatDecimal, formatMoney, formatPercent, playTypeLabel, selectionLabel } from "../utils/format";
import { dominantOutcome, hasCompleteResult, outcomeLabel, predictionHit, predictionProbabilities, resultOutcome } from "../utils/matchAnalytics";

function dedupeAndSortEvSignals(rows: EvSignal[]): EvSignal[] {
  const latest = new Map<string, EvSignal>();
  for (const signal of rows) {
    const key = `${signal.play_type}:${signal.selection}`;
    const current = latest.get(key);
    if (!current || String(signal.created_at || "") > String(current.created_at || "")) {
      latest.set(key, signal);
    }
  }
  return [...latest.values()].sort((left, right) => Number(right.ev || 0) - Number(left.ev || 0)).slice(0, 20);
}

export function MatchDetailPage() {
  const { matchId = "" } = useParams();
  const { token } = useAuth();
  const { addLeg } = useBetSlip();
  const [match, setMatch] = useState<Match | null>(null);
  const [history, setHistory] = useState<OddsSnapshot[]>([]);
  const [suggestion, setSuggestion] = useState<Suggestion | null>(null);
  const [teamForm, setTeamForm] = useState<TeamFormResponse | null>(null);
  const [predictionHistory, setPredictionHistory] = useState<PredictionHistoryResponse | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        setError("");
        const detail = await apiGet<Match>(`/matches/${encodeURIComponent(matchId)}`);
        if (cancelled) return;
        setMatch(detail);
        const [historyRows, formRows, predictionRows] = await Promise.all([
          safeGet<OddsSnapshot[]>(`/matches/${encodeURIComponent(matchId)}/odds-history?play_type=had`, []),
          safeGet<TeamFormResponse | null>(`/matches/${encodeURIComponent(matchId)}/team-form`, null),
          safeGet<PredictionHistoryResponse | null>(`/matches/${encodeURIComponent(matchId)}/prediction-history`, null),
        ]);
        if (cancelled) return;
        setHistory(historyRows);
        setTeamForm(formRows);
        setPredictionHistory(predictionRows);
        if (token) {
          setSuggestion(await safeGet<Suggestion | null>(`/model/suggestion?match_id=${encodeURIComponent(matchId)}`, null, token));
        } else {
          setSuggestion(null);
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "比赛详情加载失败");
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [matchId, token]);

  const had = useMemo(() => match?.latest_odds?.find((row) => row.play_type === "had"), [match]);
  const matrix = match?.latest_prediction?.score_matrix || null;
  const evSignals = useMemo(() => dedupeAndSortEvSignals(match?.ev_signals || []), [match?.ev_signals]);
  const isFinished = match ? hasCompleteResult(match) : false;

  if (error) return <div className="rounded-lg border border-danger/40 bg-danger/10 p-4 text-sm">{error}</div>;
  if (!match) return <div className="rounded-lg border border-white/10 p-5 text-paper/65">比赛详情加载中</div>;

  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_360px]">
      <div className="space-y-5">
        <section className="rounded-lg border border-white/10 bg-white/[0.06] p-5 shadow-soft">
          <div className="text-sm text-paper/55">{match.match_num} · {formatDateTime(match.kickoff_at)}</div>
          <h1 className="mt-2 text-2xl font-semibold md:text-3xl">
            {match.home_team} <span className="text-paper/35">vs</span> {match.away_team}
          </h1>
          {isFinished ? (
            <div className="mt-5 rounded-lg bg-black/15 px-4 py-5 text-center text-4xl font-bold text-gold">
              {match.result_home}:{match.result_away}
            </div>
          ) : null}
          <div className="mt-5">
            {match.latest_prediction ? (
              <div className="space-y-3">
                <MetricHelp glossaryKey="modelPrediction" />
                <ProbabilityBar prediction={match.latest_prediction} />
              </div>
            ) : (
              <p className="text-sm text-paper/60">{match.prediction_status?.message || "该场暂未开售胜平负，预测生成中"}</p>
            )}
          </div>
          <div className="mt-4">
            {isFinished ? (
              <Link
                to={`/recaps/${encodeURIComponent(match.match_id)}`}
                className="inline-flex items-center rounded-lg border border-gold/45 px-3 py-2 text-sm font-medium text-gold transition hover:bg-gold/10"
              >
                查看赛后复盘
              </Link>
            ) : (
              <span className="text-sm text-paper/45">赛后复盘将在比赛结束后生成</span>
            )}
          </div>
        </section>

        <section className="rounded-lg border border-white/10 bg-white/[0.06] p-5">
          <h2 className="mb-4 text-lg font-semibold">
            最新赔率
            <InfoTip glossaryKey="odds" />
          </h2>
          <div className="grid gap-3 md:grid-cols-3">
            {had ? (
              ["3", "1", "0"].map((key) => (
                <button
                  key={key}
                  type="button"
                  onClick={() =>
                    addLeg({
                      match_id: match.match_id,
                      play_type: "had",
                      selection: key,
                      odds: had.odds[key],
                      snapshot_id: had.id,
                      label: `${match.home_team} vs ${match.away_team}`,
                    })
                  }
                  className="rounded-lg border border-white/10 bg-pitch/70 p-4 text-left transition hover:border-gold/60"
                >
                  <div className="text-sm text-paper/55">{selectionLabel(key)}</div>
                  <div className="mt-1 text-2xl font-semibold text-gold">{formatDecimal(had.odds[key])}</div>
                  <div className="mt-2 flex items-center gap-1 text-xs text-paper/55">
                    <PlusCircle size={14} /> 加入模拟注单
                  </div>
                </button>
              ))
            ) : (
              <div className="text-sm text-paper/60">暂无胜平负赔率</div>
            )}
          </div>
        </section>

        <section className="rounded-lg border border-white/10 bg-white/[0.06] p-5">
          <h2 className="mb-4 text-lg font-semibold">11x11 比分矩阵</h2>
          {matrix ? (
            <ScoreMatrix matrix={matrix} resultHome={match.result_home} resultAway={match.result_away} matchStatus={match.status} />
          ) : (
            <p className="text-sm text-paper/60">{match.prediction_status?.message || "暂未开售，等待竞彩赔率"}</p>
          )}
        </section>

        <section className="rounded-lg border border-white/10 bg-white/[0.06] p-5">
          <h2 className="mb-4 text-lg font-semibold">
            EV 信号
            <InfoTip glossaryKey="evSignal" />
          </h2>
          <MetricHelp glossaryKey="evSignal" />
          {evSignals.length ? (
            <div className="mt-4 overflow-x-auto">
              <table className="w-full min-w-[620px] text-sm">
                <thead className="text-left text-paper/45">
                  <tr>
                    <th className="py-2">玩法</th>
                    <th>选项</th>
                    <th>模型概率</th>
                    <th>赔率</th>
                    <th>
                      EV
                      <InfoTip glossaryKey="ev" />
                    </th>
                    <th>状态</th>
                  </tr>
                </thead>
                <tbody>
                  {evSignals.map((signal) => (
                    <tr key={`${signal.play_type}-${signal.selection}`} className="border-t border-white/10">
                      <td className="py-2">{playTypeLabel(signal.play_type)}</td>
                      <td>{selectionLabel(signal.selection)}</td>
                      <td>{formatPercent(signal.model_prob)}</td>
                      <td>{formatDecimal(signal.odds)}</td>
                      <td><EvBadge ev={signal.ev} /></td>
                      <td className="text-paper/60">{signal.research_only ? "研究信号" : "可观察"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-sm text-paper/60">暂无价值信号</p>
          )}
        </section>
      </div>

      <RightRail
        match={match}
        had={had}
        history={history}
        suggestion={suggestion}
        token={token}
        teamForm={teamForm}
        predictionHistory={predictionHistory}
      />
    </div>
  );
}

type RightRailProps = {
  match: Match;
  had?: OddsSnapshot;
  history: OddsSnapshot[];
  suggestion: Suggestion | null;
  token: string | null;
  teamForm: TeamFormResponse | null;
  predictionHistory: PredictionHistoryResponse | null;
};

function RightRail({ match, had, history, suggestion, token, teamForm, predictionHistory }: RightRailProps) {
  const finished = hasCompleteResult(match);
  return (
    <div className="space-y-5 lg:sticky lg:top-[88px] lg:self-start">
      {finished ? (
        <>
          <Panel title="赛果卡"><ResultCard match={match} /></Panel>
          <Panel title="模型赛前判断对照"><ModelJudgement match={match} /></Panel>
          <Panel title="复盘入口">
            <Link to={`/recaps/${encodeURIComponent(match.match_id)}`} className="block rounded-lg bg-gold px-4 py-3 text-center text-sm font-semibold text-pitch">
              查看完整赛后复盘
            </Link>
          </Panel>
        </>
      ) : (
        <>
          <Panel title="模型建议">
            <SuggestionCard suggestion={suggestion} token={token} />
          </Panel>
          <Panel title="胜平负赔率历史"><OddsHistoryMini rows={history} /></Panel>
          <BetSlipCompact />
        </>
      )}

      <Panel title="赔率走势图"><OddsTrendMini rows={history} /></Panel>
      <Panel title="模型 vs 市场对比"><MarketModelCompare prediction={match.latest_prediction} odds={had?.odds} /></Panel>
      <Panel title="关键数字卡"><ScoreMatrixSummaryCard matrix={match.latest_prediction?.score_matrix} /></Panel>
      <Panel title="两队近 5 场状态"><TeamFormMini data={teamForm} /></Panel>
      <Panel title="模型概率漂移"><PredictionDriftMini data={predictionHistory} /></Panel>
    </div>
  );
}

function Panel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="rounded-lg border border-white/10 bg-white/[0.06] p-5 shadow-soft">
      <h2 className="mb-4 text-lg font-semibold">{title}</h2>
      {children}
    </section>
  );
}

function ResultCard({ match }: { match: Match }) {
  const actual = resultOutcome(match);
  return (
    <div className="space-y-3 text-sm">
      <div className="rounded-lg bg-black/15 p-4 text-center">
        <div className="text-paper/50">{match.home_team} vs {match.away_team}</div>
        <div className="mt-2 text-3xl font-bold text-gold">{match.result_home}:{match.result_away}</div>
      </div>
      <div className="flex items-center justify-between rounded-lg bg-white/5 px-3 py-2">
        <span className="text-paper/60">赛果方向</span>
        <span>{outcomeLabel(actual)}</span>
      </div>
    </div>
  );
}

function ModelJudgement({ match }: { match: Match }) {
  const probs = predictionProbabilities(match.latest_prediction);
  const predicted = dominantOutcome(probs);
  const hit = predictionHit(match, match.latest_prediction);
  return (
    <div className="space-y-2 text-sm">
      <div className="flex items-center justify-between rounded-lg bg-white/5 px-3 py-2">
        <span className="text-paper/60">赛前方向</span>
        <span>{outcomeLabel(predicted)}</span>
      </div>
      <div className="flex items-center justify-between rounded-lg bg-white/5 px-3 py-2">
        <span className="text-paper/60">赛前概率</span>
        <span>{predicted && probs ? formatPercent(probs[predicted]) : "-"}</span>
      </div>
      <div className="flex items-center justify-between rounded-lg bg-white/5 px-3 py-2">
        <span className="text-paper/60">对照结果</span>
        <span className={hit ? "text-emerald-200" : "text-gold"}>{hit === null ? "无预测" : hit ? "模型命中" : "模型未命中"}</span>
      </div>
    </div>
  );
}

function SuggestionCard({ suggestion, token }: { suggestion: Suggestion | null; token: string | null }) {
  if (!token) {
    return <p className="text-sm text-paper/60">登录后查看模型建议金额。</p>;
  }
  if (!suggestion) {
    return <p className="text-sm text-paper/60">建议加载中</p>;
  }
  return (
    <div className="space-y-3 text-sm">
      <EvBadge ev={suggestion.ev} />
      <div className="text-paper/70">
        {suggestion.play_type ? `${playTypeLabel(suggestion.play_type)} · ${selectionLabel(suggestion.selection || "")}` : "暂无正 EV"}
      </div>
      <div className="rounded-lg bg-pitch/70 p-4">
        <div className="text-paper/55">Kelly/4 建议金额</div>
        <div className="mt-1 text-2xl font-semibold text-gold">{formatMoney(suggestion.suggested_stake)}</div>
        <div className="mt-2 text-xs text-paper/50">当前投注功能关闭；这里仅用于虚拟资金模拟，不是投注建议。</div>
      </div>
    </div>
  );
}

async function safeGet<T>(path: string, fallback: T, token?: string | null): Promise<T> {
  try {
    return await apiGet<T>(path, token);
  } catch {
    return fallback;
  }
}
