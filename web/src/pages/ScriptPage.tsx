import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { useSearchParams } from "react-router-dom";
import { Film, RefreshCw } from "lucide-react";
import { apiGet } from "../api/client";
import type { ScriptMatchItem, ScriptMatchesResponse, ScriptOverview } from "../api/types";
import { formatPercent } from "../utils/format";

const GROUPS = ["A-L", "A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L"];

export function ScriptPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const groupParam = normalizeGroupParam(searchParams.get("group"));
  const targetTeam = searchParams.get("team") || "";
  const [overview, setOverview] = useState<ScriptOverview | null>(null);
  const [matches, setMatches] = useState<ScriptMatchItem[]>([]);
  const [group, setGroup] = useState(() => groupParam || "A-L");
  const [highlightedId, setHighlightedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (groupParam && groupParam !== group) setGroup(groupParam);
  }, [group, groupParam]);

  useEffect(() => {
    let active = true;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const [overviewData, matchData] = await Promise.all([
          apiGet<ScriptOverview>("/script/overview"),
          apiGet<ScriptMatchesResponse>(`/script/matches?stage=group&group=${encodeURIComponent(group)}`),
        ]);
        if (!active) return;
        setOverview(overviewData);
        setMatches(matchData.matches || []);
      } catch (err) {
        if (!active) return;
        setError(err instanceof Error ? err.message : "剧本对照暂时不可用");
      } finally {
        if (active) setLoading(false);
      }
    }
    load();
    return () => {
      active = false;
    };
  }, [group]);

  const targetId = targetTeam ? scriptCardIdFromTeamParam(targetTeam) : "";

  useEffect(() => {
    if (loading || error || !targetId) return;
    let fadeTimer: number | undefined;
    const scrollTimer = window.setTimeout(() => {
      const target = document.getElementById(targetId);
      if (!target) return;
      target.scrollIntoView({ behavior: "smooth", block: "center" });
      setHighlightedId(targetId);
      fadeTimer = window.setTimeout(() => {
        setHighlightedId((current) => (current === targetId ? null : current));
      }, 2400);
    }, 150);
    return () => {
      window.clearTimeout(scrollTimer);
      if (fadeTimer) window.clearTimeout(fadeTimer);
    };
  }, [error, loading, matches, targetId]);

  const sentence = useMemo(() => buildOverviewSentence(overview), [overview]);

  function handleGroupClick(item: string) {
    setGroup(item);
    setHighlightedId(null);
    const next = new URLSearchParams(searchParams);
    if (item === "A-L") next.delete("group");
    else next.set("group", item);
    next.delete("team");
    setSearchParams(next, { replace: true });
  }

  return (
    <div className="mx-auto max-w-7xl space-y-5">
      <section className="overflow-hidden rounded-xl border border-[#8b6b2a]/50 bg-[#071428] text-[#f6ead0] shadow-2xl shadow-black/20">
        <div className="bg-[radial-gradient(circle_at_top_right,rgba(202,164,82,0.30),transparent_32%),linear-gradient(135deg,#08172e,#0b2340)] px-4 py-5 sm:px-6 sm:py-7">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            <div className="max-w-3xl">
              <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-[#caa452]/40 bg-[#caa452]/12 px-3 py-1 text-xs font-semibold text-[#f1c968]">
                <Film size={15} />
                剧本 vs 真实
              </div>
              <h1 className="text-2xl font-black tracking-wide text-white sm:text-4xl">看剧本怎么被现实打脸</h1>
              <p className="mt-3 max-w-2xl text-sm leading-7 text-[#f6ead0]/82 sm:text-base">
                这是商业剧本推演，不是预测。真实足球只服从概率，不服从剧本。
              </p>
            </div>
            <div className="rounded-lg border border-[#caa452]/35 bg-black/20 px-4 py-3 text-sm leading-6 text-[#f6ead0]/80">
              反面教材：别信剧本，信概率。这里展示的是娱乐和认知对照，不是投注建议。
            </div>
          </div>
        </div>
      </section>

      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <OverviewCard label="剧本方向命中" value={formatRate(overview?.script_direction_accuracy ?? overview?.direction_accuracy)} />
        <OverviewCard label="剧本比分命中" value={formatRate(overview?.script_exact_accuracy ?? overview?.exact_accuracy)} />
        <OverviewCard label="剧本推演场" value={`${overview?.script_count ?? 0} 场`} />
        <OverviewCard label="已知赛果样本" value={`${overview?.real_count ?? 0} 场`} />
      </section>

      <section className="rounded-xl border border-[#caa452]/25 bg-[#0a1b33] px-4 py-4 text-[#f6ead0]">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <p className="text-sm leading-6 text-[#f6ead0]/80">{sentence}</p>
          <div className="flex flex-wrap gap-2">
            {GROUPS.map((item) => (
              <button
                key={item}
                type="button"
                onClick={() => handleGroupClick(item)}
                className={`rounded-full border px-3 py-1.5 text-xs font-semibold transition ${
                  group === item
                    ? "border-[#f1c968] bg-[#f1c968] text-[#08172e]"
                    : "border-white/15 bg-white/5 text-[#f6ead0]/75 hover:bg-white/10"
                }`}
              >
                {item}
              </button>
            ))}
          </div>
        </div>
      </section>

      {loading ? <ScriptState text="剧本对照加载中..." /> : null}
      {error ? <ScriptState text={error} danger /> : null}
      {!loading && !error && matches.length === 0 ? <ScriptState text="暂无剧本对照数据。" /> : null}

      <section className="grid gap-4 lg:grid-cols-2">
        {matches.map((match, index) => {
          const cardId = scriptCardId(match.home_team, match.away_team);
          return (
            <ScriptCard
              key={`${match.group}-${match.home_team}-${match.away_team}-${index}`}
              match={match}
              cardId={cardId}
              highlighted={highlightedId === cardId}
            />
          );
        })}
      </section>
    </div>
  );
}

function OverviewCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-[#caa452]/25 bg-[#0b203b] px-4 py-4 text-[#f6ead0]">
      <div className="text-xs text-[#f6ead0]/55">{label}</div>
      <div className="mt-2 text-2xl font-black text-[#f1c968]">{value}</div>
    </div>
  );
}

function ScriptCard({ match, cardId, highlighted }: { match: ScriptMatchItem; cardId: string; highlighted: boolean }) {
  const badge = badgeFor(match);
  const tone = highlighted
    ? "border-[#f1c968] bg-[#14345d] shadow-[0_0_0_3px_rgba(241,201,104,0.22)]"
    : "border-[#caa452]/22 bg-[#08172e] shadow-lg shadow-black/15";
  return (
    <article id={cardId} className={`scroll-mt-24 rounded-xl border p-4 text-[#f6ead0] transition-all duration-700 ${tone}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-xs font-semibold uppercase tracking-wide text-[#caa452]">
            {match.group}组 · {match.match_num || "剧本场次"}
          </div>
          <h2 className="mt-2 text-lg font-black text-white">
            {match.home_team} vs {match.away_team}
          </h2>
        </div>
        <span className={`rounded-full px-3 py-1 text-xs font-bold ${badge.className}`}>{badge.text}</span>
      </div>

      <div className="mt-4 space-y-3 text-sm leading-6">
        <InfoLine label="🎬 剧本说">
          {match.home_team} {match.script_score} {match.away_team}
          {match.narrative ? <span className="ml-1 text-[#f6ead0]/62">「{match.narrative}」</span> : null}
        </InfoLine>
        <InfoLine label="⚽ 真实是">
          {match.real_score ? `${match.real_score} [${match.status}]` : match.status === "NOT_YET" ? "即将开赛" : "真实待揭晓"}
        </InfoLine>
        <InfoLine label="📊 模型概率">{modelProbText(match.model_prob)}</InfoLine>
        {match.is_real ? (
          <InfoLine label="样本类型">
            已知赛果样本：这场是已踢真实比分标注，不计入剧本预测能力。
          </InfoLine>
        ) : null}
        <InfoLine label="💬 一句点醒">
          <span className="text-[#f1c968]">{match.comment}</span>
        </InfoLine>
      </div>
    </article>
  );
}

function InfoLine({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="rounded-lg border border-white/8 bg-white/[0.035] px-3 py-2">
      <div className="text-xs font-semibold text-[#f6ead0]/48">{label}</div>
      <div className="mt-1 text-[#f6ead0]/88">{children}</div>
    </div>
  );
}

function ScriptState({ text, danger = false }: { text: string; danger?: boolean }) {
  return (
    <div className={`flex items-center gap-2 rounded-xl border px-4 py-4 text-sm ${danger ? "border-red-400/35 bg-red-500/10 text-red-100" : "border-[#caa452]/25 bg-[#0b203b] text-[#f6ead0]/75"}`}>
      <RefreshCw size={16} className={danger ? "" : "animate-spin"} />
      {text}
    </div>
  );
}

function badgeFor(match: ScriptMatchItem): { text: string; className: string } {
  if (match.is_real) {
    return { text: "已知赛果样本", className: "bg-[#7f6b38] text-[#fff3cf]" };
  }
  if (match.status !== "COMPARED") {
    return { text: "等待现实", className: "bg-slate-700 text-slate-100" };
  }
  if (match.exact_hit) {
    return { text: "比分命中", className: "bg-[#f1c968] text-[#08172e]" };
  }
  if (match.direction_hit) {
    return { text: "方向命中", className: "bg-blue-500/25 text-blue-100" };
  }
  return { text: "剧本崩了", className: "bg-red-500/25 text-red-100" };
}

function modelProbText(prob: ScriptMatchItem["model_prob"]): string {
  if (!prob) return "无模型概率";
  return `主胜 ${formatPercent(prob.home)} · 平 ${formatPercent(prob.draw)} · 客胜 ${formatPercent(prob.away)}`;
}

function formatRate(value: number | null | undefined): string {
  return value === null || value === undefined ? "待揭晓" : formatPercent(value);
}

function buildOverviewSentence(overview: ScriptOverview | null): string {
  const scriptCount = overview?.script_count ?? 0;
  const realCount = overview?.real_count ?? 0;
  if (!overview || scriptCount === 0 || overview.script_exact_accuracy === null) {
    return `剧本真实推演场还没有足够样本；另有 ${realCount} 场为已知真实比分标注样本，不计入预测能力。`;
  }
  return `剧本真实推演场：${scriptCount} 场；方向命中 ${overview.script_direction_hits ?? 0} / ${scriptCount}，比分命中 ${overview.script_exact_hits ?? 0} / ${scriptCount}。另有 ${realCount} 场为已知真实比分标注样本，不计入预测能力。`;
}

function normalizeGroupParam(value: string | null): string | null {
  if (!value) return null;
  const normalized = value.trim().toUpperCase();
  return GROUPS.includes(normalized) ? normalized : null;
}

function scriptCardId(home: string, away: string): string {
  return scriptCardIdFromTeamParam(`${home}-${away}`);
}

function scriptCardIdFromTeamParam(team: string): string {
  return `script-${safeDomId(team)}`;
}

function safeDomId(value: string): string {
  return encodeURIComponent(value.trim()).replace(/%/g, "_").replace(/[^a-zA-Z0-9_-]/g, "_");
}
