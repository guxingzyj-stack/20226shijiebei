import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { PlusCircle } from "lucide-react";
import { apiGet } from "../api/client";
import type { EvSignal, Match, OddsSnapshot, Suggestion } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { useBetSlip } from "../bet/BetSlipContext";
import { BetSlipCompact } from "../components/BetSlip";
import { EvBadge } from "../components/EvBadge";
import { OddsHistoryMini } from "../components/OddsHistoryMini";
import { ProbabilityBar } from "../components/ProbabilityBar";
import { ScoreMatrix } from "../components/ScoreMatrix";
import { formatDateTime, formatDecimal, formatMoney, formatPercent, playTypeLabel, selectionLabel } from "../utils/format";

function dedupeAndSortEvSignals(rows: EvSignal[]): EvSignal[] {
  const latest = new Map<string, EvSignal>();
  for (const signal of rows) {
    const key = `${signal.play_type}:${signal.selection}`;
    const current = latest.get(key);
    if (!current || String(signal.created_at || "") > String(current.created_at || "")) {
      latest.set(key, signal);
    }
  }
  return [...latest.values()]
    .sort((left, right) => Number(right.ev || 0) - Number(left.ev || 0))
    .slice(0, 20);
}

function hasFinishedResult(match: Match): boolean {
  return (
    ["finished", "completed"].includes(match.status) &&
    match.result_home !== null &&
    match.result_home !== undefined &&
    match.result_away !== null &&
    match.result_away !== undefined
  );
}

export function MatchDetailPage() {
  const { matchId = "" } = useParams();
  const { token } = useAuth();
  const { addLeg } = useBetSlip();
  const [match, setMatch] = useState<Match | null>(null);
  const [history, setHistory] = useState<OddsSnapshot[]>([]);
  const [suggestion, setSuggestion] = useState<Suggestion | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    async function load() {
      try {
        const detail = await apiGet<Match>(`/matches/${encodeURIComponent(matchId)}`);
        setMatch(detail);
        setHistory(await apiGet<OddsSnapshot[]>(`/matches/${encodeURIComponent(matchId)}/odds-history?play_type=had`));
        if (token) {
          setSuggestion(await apiGet<Suggestion>(`/model/suggestion?match_id=${encodeURIComponent(matchId)}`, token));
        } else {
          setSuggestion(null);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "比赛详情加载失败");
      }
    }
    load();
  }, [matchId, token]);

  const had = useMemo(() => match?.latest_odds?.find((row) => row.play_type === "had"), [match]);
  const matrix = match?.latest_prediction?.score_matrix || null;
  const evSignals = useMemo(() => dedupeAndSortEvSignals(match?.ev_signals || []), [match?.ev_signals]);

  if (error) return <div className="rounded-lg border border-danger/40 bg-danger/10 p-4 text-sm">{error}</div>;
  if (!match) return <div className="rounded-lg border border-white/10 p-5 text-paper/65">比赛详情加载中</div>;

  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_340px]">
      <div className="space-y-5">
        <section className="rounded-lg border border-white/10 bg-white/[0.06] p-5 shadow-soft">
          <div className="text-sm text-paper/55">{match.match_num} · {formatDateTime(match.kickoff_at)}</div>
          <h1 className="mt-2 text-2xl font-semibold md:text-3xl">
            {match.home_team} <span className="text-paper/35">vs</span> {match.away_team}
          </h1>
          <div className="mt-5">
            {match.latest_prediction ? (
              <ProbabilityBar prediction={match.latest_prediction} />
            ) : (
              <p className="text-sm text-paper/60">{match.prediction_status?.message || "该场暂未开售胜平负，预测生成中"}</p>
            )}
          </div>
          <div className="mt-4">
            {hasFinishedResult(match) ? (
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
          <h2 className="mb-4 text-lg font-semibold">最新赔率</h2>
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
          {matrix ? <ScoreMatrix matrix={matrix} /> : <p className="text-sm text-paper/60">{match.prediction_status?.message || "暂未开售，等待竞彩赔率"}</p>}
        </section>

        <section className="rounded-lg border border-white/10 bg-white/[0.06] p-5">
          <h2 className="mb-4 text-lg font-semibold">EV 信号</h2>
          {evSignals.length ? (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[620px] text-sm">
                <thead className="text-left text-paper/45">
                  <tr>
                    <th className="py-2">玩法</th>
                    <th>选项</th>
                    <th>模型概率</th>
                    <th>赔率</th>
                    <th>EV</th>
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
                      <td className="text-paper/60">{signal.research_only ? "分歧过大，仅供研究" : "可观察"}</td>
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

      <div className="space-y-5">
        <section className="rounded-lg border border-white/10 bg-white/[0.06] p-5">
          <h2 className="text-lg font-semibold">模型建议</h2>
          {token ? (
            suggestion ? (
              <div className="mt-4 space-y-3 text-sm">
                <EvBadge ev={suggestion.ev} />
                <div className="text-paper/70">
                  {suggestion.play_type ? `${playTypeLabel(suggestion.play_type)} · ${selectionLabel(suggestion.selection || "")}` : "暂无正 EV"}
                </div>
                <div className="rounded-lg bg-pitch/70 p-4">
                  <div className="text-paper/55">Kelly/4 建议金额</div>
                  <div className="mt-1 text-2xl font-semibold text-gold">{formatMoney(suggestion.suggested_stake)}</div>
                  <div className="mt-2 text-xs text-paper/50">已按余额 5% 上限控制，仅供虚拟资金模拟。</div>
                </div>
              </div>
            ) : (
              <p className="mt-3 text-sm text-paper/60">建议加载中</p>
            )
          ) : (
            <p className="mt-3 text-sm text-paper/60">登录后查看模型建议金额。</p>
          )}
        </section>
        <section className="rounded-lg border border-white/10 bg-white/[0.06] p-5">
          <h2 className="mb-4 text-lg font-semibold">胜平负赔率历史</h2>
          <OddsHistoryMini rows={history} />
        </section>
        <BetSlipCompact />
      </div>
    </div>
  );
}
