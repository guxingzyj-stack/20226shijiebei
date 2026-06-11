import { Link } from "react-router-dom";
import { useEffect, useMemo, useState } from "react";
import { ChevronRight } from "lucide-react";
import { apiGet } from "../api/client";
import type { Match } from "../api/types";
import { EvBadge } from "../components/EvBadge";
import { ProbabilityBar } from "../components/ProbabilityBar";
import { formatDateKey, formatDateTime } from "../utils/format";

export function MatchesPage() {
  const [matches, setMatches] = useState<Match[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        setLoading(true);
        const baseMatches = await apiGet<Match[]>("/matches?status=upcoming");
        if (cancelled) return;
        setMatches(baseMatches);
      } catch (err) {
        setError(err instanceof Error ? err.message : "赛程加载失败");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, []);

  const grouped = useMemo(() => {
    return matches.reduce<Record<string, Match[]>>((groups, match) => {
      const key = formatDateKey(match.kickoff_at);
      groups[key] = [...(groups[key] || []), match];
      return groups;
    }, {});
  }, [matches]);

  return (
    <div className="space-y-6">
      <section className="rounded-lg border border-white/10 bg-white/[0.06] p-5 shadow-soft">
        <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
          <div>
            <p className="text-sm font-medium text-gold">虚拟资金模拟游戏</p>
            <h1 className="mt-1 text-2xl font-semibold md:text-3xl">世界杯赛程总览</h1>
          </div>
          <p className="max-w-xl text-sm leading-6 text-paper/68">
            这里展示模型融合概率、最新竞彩赔率和 EV 信号。所有操作仅用于模拟娱乐，不涉及真实购彩。
          </p>
        </div>
      </section>

      {loading ? <div className="rounded-lg border border-white/10 p-5 text-paper/65">赛程加载中</div> : null}
      {error ? <div className="rounded-lg border border-danger/40 bg-danger/10 p-4 text-sm text-paper">{error}</div> : null}

      {Object.entries(grouped).map(([date, rows]) => (
        <section key={date} className="space-y-3">
          <h2 className="text-sm font-semibold text-gold">{date}</h2>
          <div className="grid gap-3 lg:grid-cols-2">
            {rows.map((match) => {
              const topEv = match.ev_signals?.find((signal) => !signal.research_only);
              const hasPrediction = Boolean(match.latest_prediction);
              return (
                <Link
                  key={match.match_id}
                  to={`/matches/${encodeURIComponent(match.match_id)}`}
                  className="rounded-lg border border-white/10 bg-white/[0.055] p-4 transition hover:border-gold/55 hover:bg-white/[0.08]"
                >
                  <div className="mb-4 flex items-start justify-between gap-3">
                    <div>
                      <div className="text-xs text-paper/50">
                        {match.match_num || match.league} · {formatDateTime(match.kickoff_at)}
                      </div>
                      <div className="mt-2 text-lg font-semibold">
                        {match.home_team} <span className="text-paper/35">vs</span> {match.away_team}
                      </div>
                    </div>
                    <ChevronRight className="shrink-0 text-paper/45" size={20} />
                  </div>
                  <div className="grid gap-4 md:grid-cols-[1fr_auto] md:items-center">
                    {hasPrediction ? (
                      <ProbabilityBar prediction={match.latest_prediction} />
                    ) : (
                      <div className="text-sm text-paper/60">{match.prediction_status?.message || "暂未开售，等待竞彩赔率"}</div>
                    )}
                    {hasPrediction ? (
                      <EvBadge ev={topEv?.ev} />
                    ) : (
                      <span className="rounded-full border border-white/12 px-3 py-1 text-xs font-medium text-paper/65">暂未开售</span>
                    )}
                  </div>
                </Link>
              );
            })}
          </div>
        </section>
      ))}
    </div>
  );
}
