import { Link, useSearchParams } from "react-router-dom";
import { useEffect, useMemo, useState } from "react";
import { ChevronRight, GitBranch } from "lucide-react";
import { apiGet } from "../api/client";
import type { Match } from "../api/types";
import { EvBadge } from "../components/EvBadge";
import { MetricHelp } from "../components/MetricHelp";
import { ProbabilityBar } from "../components/ProbabilityBar";
import { formatDateKey, formatDateTime, formatPercent } from "../utils/format";
import { dominantOutcome, hasCompleteResult, outcomeLabel, predictionHit, predictionProbabilities } from "../utils/matchAnalytics";

const FILTERS = [
  { key: "all", label: "全部" },
  { key: "upcoming", label: "未开赛" },
  { key: "finished", label: "已完赛" },
] as const;

type FilterKey = (typeof FILTERS)[number]["key"];

export function MatchesPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const activeFilter = normalizeFilter(searchParams.get("status"));
  const [matches, setMatches] = useState<Match[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        setLoading(true);
        setError("");
        const baseMatches = await apiGet<Match[]>(`/matches?status=${activeFilter}`);
        if (!cancelled) setMatches(baseMatches);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "赛程加载失败");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [activeFilter]);

  const sortedMatches = useMemo(() => sortTodayFirst(matches), [matches]);
  const grouped = useMemo(() => {
    return sortedMatches.reduce<Record<string, Match[]>>((groups, match) => {
      const key = formatDateKey(match.kickoff_at);
      groups[key] = [...(groups[key] || []), match];
      return groups;
    }, {});
  }, [sortedMatches]);

  return (
    <div className="space-y-6">
      <section className="rounded-lg border border-white/10 bg-white/[0.06] p-5 shadow-soft">
        <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
          <div>
            <p className="text-sm font-medium text-gold">虚拟资金模拟游戏</p>
            <h1 className="mt-1 text-2xl font-semibold md:text-3xl">世界杯赛程总览</h1>
          </div>
          <p className="max-w-xl text-sm leading-6 text-paper/68">
            这里展示模型融合概率、最新竞彩赔率和 EV 研究信号。所有操作仅用于模拟娱乐，不涉及真实购彩。
          </p>
        </div>
      </section>

      <Link
        to="/bracket"
        className="flex flex-col gap-3 rounded-lg border border-gold/25 bg-gold/10 p-4 transition hover:border-gold/55 hover:bg-gold/15 sm:flex-row sm:items-center sm:justify-between"
      >
        <div className="flex min-w-0 gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-gold/35 bg-pitch/70">
            <GitBranch size={20} className="text-gold" />
          </div>
          <div className="min-w-0">
            <div className="font-semibold text-paper">世界杯预测晋级图</div>
            <p className="mt-1 text-sm leading-5 text-paper/62">查看模型预测的冠军路径和真实晋级进展。</p>
          </div>
        </div>
        <span className="inline-flex w-fit items-center rounded-lg bg-gold px-3 py-2 text-sm font-semibold text-pitch">
          查看晋级图
        </span>
      </Link>

      <div className="-mx-3 flex gap-2 overflow-x-auto px-3 pb-1 sm:mx-0 sm:flex-wrap sm:px-0">
        {FILTERS.map((filter) => (
          <button
            key={filter.key}
            type="button"
            onClick={() => setSearchParams(filter.key === "all" ? {} : { status: filter.key })}
            className={`min-w-[86px] rounded-full border px-4 py-2 text-sm font-medium transition ${
              activeFilter === filter.key ? "border-gold bg-gold text-pitch" : "border-white/12 text-paper/70 hover:border-gold/50"
            }`}
          >
            {filter.label}
          </button>
        ))}
      </div>

      <MetricHelp title="这是什么？">
        赛程页展示赛前模型概率、当前赔率和赛后复盘入口。已停售但未出赛果的比赛会显示为“赛果回填中”，不代表系统故障。
      </MetricHelp>

      {loading ? <div className="rounded-lg border border-white/10 p-5 text-paper/65">赛程加载中</div> : null}
      {error ? <div className="rounded-lg border border-danger/40 bg-danger/10 p-4 text-sm text-paper">{error}</div> : null}
      {!loading && !error && !sortedMatches.length ? <div className="rounded-lg border border-white/10 p-5 text-paper/65">暂无符合条件的比赛</div> : null}

      {Object.entries(grouped).map(([date, rows]) => (
        <section key={date} className="space-y-3">
          <h2 className="text-sm font-semibold text-gold">{date}</h2>
          <div className="grid gap-3 lg:grid-cols-2">
            {rows.map((match) => <MatchCard key={match.match_id} match={match} />)}
          </div>
        </section>
      ))}
    </div>
  );
}

function MatchCard({ match }: { match: Match }) {
  const topEv = match.ev_signals?.find((signal) => !signal.research_only);
  const hasPrediction = Boolean(match.latest_prediction);
  const completeResult = hasCompleteResult(match);
  const linkTo = completeResult ? `/recaps/${encodeURIComponent(match.match_id)}` : `/matches/${encodeURIComponent(match.match_id)}`;
  const hit = predictionHit(match, match.latest_prediction);
  const probs = predictionProbabilities(match.latest_prediction);
  const predicted = dominantOutcome(probs);
  const predictedProb = predicted && probs ? probs[predicted] : null;

  return (
    <Link
      to={linkTo}
      className="rounded-lg border border-white/10 bg-white/[0.055] p-4 transition hover:border-gold/55 hover:bg-white/[0.08]"
    >
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
                  <div className="text-xs text-paper/50">
            {match.match_num || match.league} · {formatDateTime(match.kickoff_at)}
          </div>
          <div className="mt-2 break-words text-lg font-semibold">
            {match.home_team} <span className="text-paper/35">vs</span> {match.away_team}
          </div>
        </div>
        <ChevronRight className="shrink-0 text-paper/45" size={20} />
      </div>

      {completeResult ? (
        <div className="space-y-3">
          <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-2 rounded-lg bg-black/15 px-3 py-4 text-center">
            <span className="break-words text-sm font-semibold sm:text-lg">{match.home_team}</span>
            <span className="whitespace-nowrap text-3xl font-bold text-gold">{match.result_home} - {match.result_away}</span>
            <span className="break-words text-sm font-semibold sm:text-lg">{match.away_team}</span>
          </div>
          <div className="grid gap-2 text-sm text-paper/65 md:grid-cols-2">
            <span>
              赛前判断：{outcomeLabel(predicted)}
              {predictedProb !== null ? ` ${formatPercent(predictedProb)}` : ""}
            </span>
            <span className={hit ? "text-emerald-200" : "text-gold"}>{hit === null ? "无预测" : hit ? "模型命中" : "模型未命中"}</span>
          </div>
        </div>
      ) : ["finished", "completed"].includes(match.status) ? (
        <div className="text-sm text-gold">赛果回填中</div>
      ) : (
        <div className="grid gap-4 md:grid-cols-[1fr_auto] md:items-center">
          {hasPrediction ? (
            <ProbabilityBar prediction={match.latest_prediction} />
          ) : (
            <div className="text-sm text-paper/60">{match.prediction_status?.message || "暂未开售，等待竞彩赔率"}</div>
          )}
          {hasPrediction ? (
            <EvBadge ev={topEv?.ev} />
          ) : (
            <span className="rounded-full border border-white/12 px-3 py-1 text-xs font-medium text-paper/65">接近开赛</span>
          )}
        </div>
      )}
    </Link>
  );
}

function normalizeFilter(value: string | null): FilterKey {
  return value === "upcoming" || value === "finished" ? value : "all";
}

function sortTodayFirst(matches: Match[]): Match[] {
  const today = new Intl.DateTimeFormat("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
  const dateKey = (value: string) => new Intl.DateTimeFormat("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(value));
  return [...matches].sort((left, right) => {
    const leftToday = dateKey(left.kickoff_at) === today ? 0 : 1;
    const rightToday = dateKey(right.kickoff_at) === today ? 0 : 1;
    if (leftToday !== rightToday) return leftToday - rightToday;
    return new Date(left.kickoff_at).getTime() - new Date(right.kickoff_at).getTime();
  });
}
