import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import { ChevronDown, ChevronUp, MessageCircle, PlusCircle } from "lucide-react";
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
import { hasCompleteResult } from "../utils/matchAnalytics";

const BETTING_ENABLED = import.meta.env.VITE_BETTING_ENABLED === "true";

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
  const [showData, setShowData] = useState(false);
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
        <div className="mt-5 rounded-lg border border-gold/20 bg-gold/10 p-4">
          <div className="text-xl font-semibold text-paper">{match.verdict || "模型认为这场势均力敌"}</div>
          <div className="mt-3 flex gap-2 text-sm leading-6 text-paper/72">
            <MessageCircle size={17} className="mt-1 shrink-0 text-gold" />
            <span>{match.banter || "看球图乐，赔率背后庄家早算好了账。"}</span>
          </div>
        </div>
        {!match.latest_prediction ? (
          <p className="mt-4 text-sm text-paper/60">{match.prediction_status?.message || "预测生成中"}</p>
        ) : null}
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
        <h2 className="mb-4 text-lg font-semibold">11x11 比分矩阵</h2>
        {matrix ? (
          <ScoreMatrix matrix={matrix} resultHome={match.result_home} resultAway={match.result_away} matchStatus={match.status} />
        ) : (
          <p className="text-sm text-paper/60">{match.prediction_status?.message || "比分矩阵生成中"}</p>
        )}
      </section>

      <button
        type="button"
        onClick={() => setShowData((value) => !value)}
        className="inline-flex w-full items-center justify-center gap-2 rounded-lg border border-gold/40 bg-gold/10 px-4 py-3 text-sm font-semibold text-gold transition hover:bg-gold/15 sm:w-auto"
      >
        {showData ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
        {showData ? "收起数据详情" : "查看数据详情"}
      </button>

      {showData ? (
        <div className="grid min-w-0 gap-5 lg:grid-cols-[minmax(0,1fr)_360px]">
          <div className="min-w-0 space-y-5">
            <section className="rounded-lg border border-white/10 bg-white/[0.06] p-5">
              <h2 className="mb-4 text-lg font-semibold">
                模型概率
                <InfoTip glossaryKey="modelPrediction" />
              </h2>
              {match.latest_prediction ? <ProbabilityBar prediction={match.latest_prediction} /> : <p className="text-sm text-paper/60">暂无模型概率</p>}
            </section>

            <section className="rounded-lg border border-white/10 bg-white/[0.06] p-5">
              <h2 className="mb-4 text-lg font-semibold">
                市场赔率与抽水
                <InfoTip glossaryKey="odds" />
              </h2>
              <LatestOddsGrid match={match} had={had} onAddLeg={addLeg} />
              <VigNotice match={match} hasPositiveEv={evSignals.some((signal) => Number(signal.ev || 0) > 0)} />
            </section>

            <section className="rounded-lg border border-white/10 bg-white/[0.06] p-5">
              <h2 className="mb-4 text-lg font-semibold">
                模型 vs 市场
                <InfoTip glossaryKey="impliedProbability" />
              </h2>
              <MarketProbSummary match={match} />
              <div className="mt-4">
                <MarketModelCompare prediction={match.latest_prediction} odds={had?.odds} />
              </div>
            </section>

            <section className="rounded-lg border border-white/10 bg-white/[0.06] p-5">
              <h2 className="mb-4 text-lg font-semibold">
                EV 信号
                <InfoTip glossaryKey="evSignal" />
              </h2>
              <MetricHelp glossaryKey="evSignal" />
              <EvTable rows={evSignals} />
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
      ) : null}
    </div>
  );
}

function LatestOddsGrid({
  match,
  had,
  onAddLeg,
}: {
  match: Match;
  had?: OddsSnapshot;
  onAddLeg: (leg: { match_id: string; play_type: string; selection: string; odds?: string | number; snapshot_id?: number; label?: string }) => void;
}) {
  if (!had) return <div className="text-sm text-paper/60">暂无胜平负赔率</div>;
  return (
    <div className="grid gap-3 md:grid-cols-3">
      {["3", "1", "0"].map((key) => (
        <div key={key} className="rounded-lg border border-white/10 bg-pitch/70 p-4">
          <div className="text-sm text-paper/55">{selectionLabel(key)}</div>
          <div className="mt-1 text-2xl font-semibold text-gold">{formatDecimal(had.odds[key])}</div>
          {BETTING_ENABLED ? (
            <button
              type="button"
              onClick={() =>
                onAddLeg({
                  match_id: match.match_id,
                  play_type: "had",
                  selection: key,
                  odds: had.odds[key],
                  snapshot_id: had.id,
                  label: `${match.home_team} vs ${match.away_team}`,
                })
              }
              className="mt-2 flex items-center gap-1 text-xs text-paper/55 hover:text-gold"
            >
              <PlusCircle size={14} /> 加入模拟注单
            </button>
          ) : (
            <div className="mt-2 text-xs text-paper/50">仅展示，不开放下注</div>
          )}
        </div>
      ))}
    </div>
  );
}

function VigNotice({ match, hasPositiveEv }: { match: Match; hasPositiveEv: boolean }) {
  const vig = match.vig?.had?.vig;
  if (vig === null || vig === undefined) {
    return <p className="mt-4 text-sm text-paper/60">抽水率暂时无法计算。</p>;
  }
  const points = (vig * 100).toFixed(1);
  return (
    <div className="mt-4 rounded-lg border border-gold/25 bg-gold/10 p-3 text-sm leading-6 text-paper/72">
      {hasPositiveEv
        ? `这场庄家平均每 100 块先抽走 ${points} 块。模型发现了分歧点，但不代表长期盈利。`
        : `这场庄家平均每 100 块先抽走 ${points} 块，模型也没找到明显便宜。`}
    </div>
  );
}

function MarketProbSummary({ match }: { match: Match }) {
  const probs = match.market_implied_prob?.had;
  if (!probs) return <p className="text-sm text-paper/60">市场隐含概率暂不可用。</p>;
  const model = match.latest_prediction;
  const diffs = model
    ? [Math.abs(Number(model.p_home) - probs.home), Math.abs(Number(model.p_draw) - probs.draw), Math.abs(Number(model.p_away) - probs.away)]
    : [];
  const message = diffs.length && Math.max(...diffs) < 0.05 ? "模型与市场看法基本一致。" : "模型在这场和市场有分歧。";
  return (
    <div className="space-y-3">
      <div className="grid gap-2 text-sm sm:grid-cols-3">
        <Metric label="主胜" value={formatPercent(probs.home)} />
        <Metric label="平局" value={formatPercent(probs.draw)} />
        <Metric label="客胜" value={formatPercent(probs.away)} />
      </div>
      <p className="text-sm text-paper/62">{message}</p>
    </div>
  );
}

function EvTable({ rows }: { rows: EvSignal[] }) {
  if (!rows.length) return <p className="text-sm text-paper/60">暂无价值信号</p>;
  return (
    <div className="mt-4 overflow-x-auto">
      <table className="mobile-card-table w-full text-sm sm:min-w-[620px]">
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
          {rows.map((signal) => (
            <tr key={`${signal.play_type}-${signal.selection}`} className="border-t border-white/10">
              <td data-label="玩法" className="py-2">{playTypeLabel(signal.play_type)}</td>
              <td data-label="选项">{selectionLabel(signal.selection)}</td>
              <td data-label="模型概率">{formatPercent(signal.model_prob)}</td>
              <td data-label="赔率">{formatDecimal(signal.odds)}</td>
              <td data-label="EV"><EvBadge ev={signal.ev} /></td>
              <td data-label="状态" className="text-paper/60">{signal.research_only ? "研究信号，不是投注建议" : "观察信号"}</td>
            </tr>
          ))}
        </tbody>
      </table>
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
  return (
    <div className="min-w-0 space-y-5 lg:self-start">
      <Panel title="模型观察：分歧最大的玩法">
        <SuggestionCard suggestion={suggestion} token={token} />
      </Panel>
      <Panel title="胜平负赔率历史"><OddsHistoryMini rows={history} /></Panel>
      {BETTING_ENABLED ? <BetSlipCompact /> : null}
      <Panel title="赔率走势图"><OddsTrendMini rows={history} /></Panel>
      <Panel title="关键数字卡"><ScoreMatrixSummaryCard matrix={match.latest_prediction?.score_matrix} /></Panel>
      <Panel title="两队近 5 场状态"><TeamFormMini data={teamForm} /></Panel>
      <Panel title="模型概率漂移"><PredictionDriftMini data={predictionHistory} /></Panel>
      <Panel title="抽水率">
        <div className="text-sm text-paper/62">
          {match.vig?.had ? `HAD 抽水率约 ${(match.vig.had.vig * 100).toFixed(1)}%。这是庄家优势的近似值。` : "暂无可计算赔率。"}
        </div>
      </Panel>
      <Panel title="玩法说明">
        <div className="text-sm leading-6 text-paper/62">这是风险管理演示，不是盈利建议。EV 只是研究信号，不是中奖概率。</div>
      </Panel>
    </div>
  );
}

function Panel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="min-w-0 rounded-lg border border-white/10 bg-white/[0.06] p-5 shadow-soft">
      <h2 className="mb-4 text-lg font-semibold">{title}</h2>
      {children}
    </section>
  );
}

function SuggestionCard({ suggestion, token }: { suggestion: Suggestion | null; token: string | null }) {
  if (!token) {
    return <p className="text-sm text-paper/60">登录后查看模型观察结果。</p>;
  }
  if (!suggestion) {
    return <p className="text-sm text-paper/60">观察结果加载中</p>;
  }
  return (
    <div className="space-y-3 text-sm">
      <EvBadge ev={suggestion.ev} />
      <div className="text-paper/70">
        {suggestion.play_type ? `${playTypeLabel(suggestion.play_type)} · ${selectionLabel(suggestion.selection || "")}` : "暂无正 EV"}
      </div>
      <div className="rounded-lg bg-pitch/70 p-4">
        <div className="text-paper/55">风险管理演示金额</div>
        <div className="mt-1 text-2xl font-semibold text-gold">{formatMoney(suggestion.suggested_stake)}</div>
        <div className="mt-2 text-xs text-paper/50">这是风险管理演示，不是盈利建议。</div>
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-white/10 bg-pitch/65 px-3 py-2">
      <div className="text-xs text-paper/50">{label}</div>
      <div className="mt-1 text-lg font-semibold text-paper">{value}</div>
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
