import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ChevronDown, GitBranch, ShieldCheck, Trophy } from "lucide-react";
import { apiGet } from "../api/client";
import type { BracketMatch, BracketResponse, BracketRound, BracketTeam } from "../api/types";
import { formatPercent } from "../utils/format";

const emptyRounds = [
  { key: "champion", title: "冠军预测", description: "等待淘汰赛路径生成后展示冠军概率或冠军结果。" },
  { key: "final", title: "决赛", description: "暂无真实决赛对阵。" },
  { key: "semifinal", title: "半决赛", description: "暂无真实半决赛对阵。" },
  { key: "quarterfinal", title: "四分之一决赛", description: "暂无真实四分之一决赛对阵。" },
  { key: "round16", title: "十六强", description: "小组赛完成后根据真实晋级结果生成。" },
];

const emptyDesktopColumns = [
  ["16强", "8强", "4强", "半决赛"],
  ["决赛", "冠军预测 / 冠军结果"],
  ["半决赛", "4强", "8强", "16强"],
];

const roundOrder = ["round16", "quarterfinal", "semifinal", "final", "champion"];

export function BracketPage() {
  const [payload, setPayload] = useState<BracketResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        setLoading(true);
        const response = await apiGet<BracketResponse>("/bracket");
        if (!cancelled) setPayload(response);
      } catch {
        if (!cancelled) {
          setPayload({
            data_status: "not_generated",
            message: "淘汰赛对阵暂未生成。",
            rounds: [],
          });
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, []);

  const rounds = useMemo(() => normalizeRounds(payload?.rounds || []), [payload?.rounds]);
  const hasData = rounds.some((round) => round.matches.length > 0);
  const dataStatus = loading ? "loading" : hasData ? payload?.data_status || "ok" : payload?.data_status || "not_generated";

  return (
    <div className="space-y-5">
      <section className="rounded-lg border border-white/10 bg-white/[0.06] p-5 shadow-soft">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="text-sm font-medium text-gold">晋级图</p>
            <h1 className="mt-1 text-2xl font-semibold md:text-3xl">预测晋级图</h1>
            <p className="mt-3 max-w-3xl text-sm leading-6 text-paper/68">
              根据赛程、赛果和模型预测生成的世界杯晋级路径。对阵未生成时不会编造；真实数据出来后会自动显示。
            </p>
          </div>
          <div className="rounded-lg border border-gold/25 bg-gold/10 px-4 py-3 text-sm text-gold">
            data_status: {dataStatus}
          </div>
        </div>
      </section>

      {!hasData ? (
        <EmptyState loading={loading} message={payload?.message} />
      ) : (
        <BracketContent rounds={rounds} champion={payload?.champion} />
      )}

      <section className="rounded-lg border border-white/10 bg-white/[0.05] p-4">
        <div className="flex items-start gap-3">
          <ShieldCheck size={18} className="mt-0.5 shrink-0 text-gold" />
          <p className="text-sm leading-6 text-paper/66">
            真实性规则：有真实晋级数据就显示；没有数据就明确提示数据不足。页面不会硬编码球队晋级、冠军预测或淘汰赛路径。
          </p>
        </div>
      </section>
    </div>
  );
}

function EmptyState({ loading, message }: { loading: boolean; message?: string }) {
  return (
    <>
      <section className="rounded-lg border border-gold/25 bg-gold/10 p-5">
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div className="flex gap-3">
            <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border border-gold/35 bg-pitch/70">
              <GitBranch className="text-gold" size={22} />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-paper">
                {loading ? "晋级图数据读取中。" : message || "淘汰赛对阵暂未生成。"}
              </h2>
              <p className="mt-2 text-sm leading-6 text-paper/68">
                小组赛完成后，系统会根据真实赛果和模型预测生成晋级图。当前页面只显示骨架和空状态，不展示假对阵。
              </p>
            </div>
          </div>
          <Link to="/matches" className="inline-flex shrink-0 items-center justify-center rounded-lg bg-gold px-4 py-3 text-sm font-semibold text-pitch">
            查看赛程
          </Link>
        </div>
      </section>

      <section className="hidden rounded-lg border border-white/10 bg-white/[0.045] p-5 lg:block">
        <div className="mb-4 flex items-center gap-2 text-lg font-semibold">
          <Trophy size={18} className="text-gold" />
          桌面晋级图骨架
        </div>
        <div className="grid gap-4 lg:grid-cols-[1fr_0.8fr_1fr]">
          {emptyDesktopColumns.map((column, columnIndex) => (
            <div key={columnIndex} className="space-y-3">
              {column.map((title) => (
                <EmptyBracketNode key={`${columnIndex}-${title}`} title={title} />
              ))}
            </div>
          ))}
        </div>
        <p className="mt-4 text-xs leading-5 text-paper/45">
          这里预留真实晋级路径的展示结构。没有真实淘汰赛对阵时，不显示球队名、概率或晋级路线。
        </p>
      </section>

      <section className="space-y-3 lg:hidden">
        <div className="flex items-center gap-2 text-lg font-semibold">
          <Trophy size={18} className="text-gold" />
          移动端分轮次查看
        </div>
        {emptyRounds.map((round, index) => (
          <details key={round.key} open={index === 0} className="rounded-lg border border-white/10 bg-white/[0.055] p-4">
            <summary className="flex cursor-pointer list-none items-center justify-between gap-3 font-semibold">
              <span>{round.title}</span>
              <ChevronDown size={18} className="text-paper/45" />
            </summary>
            <div className="mt-3 rounded-lg border border-dashed border-white/15 bg-pitch/50 p-4 text-sm leading-6 text-paper/62">
              {round.description}
            </div>
          </details>
        ))}
      </section>
    </>
  );
}

function BracketContent({ rounds, champion }: { rounds: NormalizedRound[]; champion?: string | BracketTeam | null }) {
  const championTeam = getTeam(champion);
  const leftRounds = rounds.slice(0, Math.ceil(rounds.length / 2));
  const rightRounds = rounds.slice(Math.ceil(rounds.length / 2)).reverse();

  return (
    <>
      <section className="hidden rounded-lg border border-white/10 bg-white/[0.045] p-5 lg:block">
        <div className="mb-4 flex items-center gap-2 text-lg font-semibold">
          <Trophy size={18} className="text-gold" />
          真实晋级图
        </div>
        <div className="grid gap-4 lg:grid-cols-[1fr_0.8fr_1fr]">
          <div className="space-y-4">
            {leftRounds.map((round) => (
              <RoundColumn key={round.key} round={round} />
            ))}
          </div>
          <div className="flex flex-col justify-center gap-4">
            <ChampionCard champion={championTeam} />
          </div>
          <div className="space-y-4">
            {rightRounds.map((round) => (
              <RoundColumn key={round.key} round={round} />
            ))}
          </div>
        </div>
      </section>

      <section className="space-y-3 lg:hidden">
        <div className="flex items-center gap-2 text-lg font-semibold">
          <Trophy size={18} className="text-gold" />
          分轮次查看
        </div>
        {rounds.map((round, index) => (
          <details key={round.key} open={index === 0} className="rounded-lg border border-white/10 bg-white/[0.055] p-4">
            <summary className="flex cursor-pointer list-none items-center justify-between gap-3 font-semibold">
              <span>{round.title}</span>
              <ChevronDown size={18} className="text-paper/45" />
            </summary>
            <div className="mt-3 space-y-3">
              {round.matches.map((match, matchIndex) => (
                <MatchCard key={match.id || match.match_id || matchIndex} match={match} />
              ))}
            </div>
          </details>
        ))}
      </section>
    </>
  );
}

function RoundColumn({ round }: { round: NormalizedRound }) {
  return (
    <div>
      <h2 className="mb-2 text-sm font-semibold text-gold">{round.title}</h2>
      <div className="space-y-3">
        {round.matches.map((match, index) => (
          <MatchCard key={match.id || match.match_id || index} match={match} />
        ))}
      </div>
    </div>
  );
}

function MatchCard({ match }: { match: BracketMatch }) {
  const home = getTeam(match.home_team, match.home_flag || undefined);
  const away = getTeam(match.away_team, match.away_flag || undefined);
  const winner = getTeam(match.winner_team, match.winner_flag || undefined);
  const modelPick = getTeam(match.model_pick);

  return (
    <div className="rounded-lg border border-white/10 bg-pitch/58 p-3">
      <div className="mb-2 flex items-center justify-between gap-2 text-xs text-paper/45">
        <span>{match.match_id || match.id || match.slot || "淘汰赛"}</span>
        <span>{match.status || "未开赛"}</span>
      </div>
      <TeamRow team={home} winnerName={winner.name} probability={match.home_prob} />
      <TeamRow team={away} winnerName={winner.name} probability={match.away_prob} />
      <div className="mt-2 grid gap-2 text-xs text-paper/55">
        {match.score ? <span>比分：{match.score}</span> : null}
        {modelPick.name ? <span>模型判断：{modelPick.name}</span> : null}
        {winner.name ? <span className="text-gold">晋级：{winner.name}</span> : null}
      </div>
    </div>
  );
}

function TeamRow({ team, winnerName, probability }: { team: NormalizedTeam; winnerName?: string; probability?: string | number | null }) {
  const isWinner = Boolean(team.name && winnerName && team.name === winnerName);

  return (
    <div className={`mt-2 flex items-center gap-2 rounded-lg border px-2 py-2 ${isWinner ? "border-gold/55 bg-gold/12" : "border-white/10 bg-white/[0.04]"}`}>
      <FlagBubble team={team} highlighted={isWinner} />
      <div className="min-w-0 flex-1">
        <div className={`truncate text-sm font-semibold ${isWinner ? "text-gold" : "text-paper"}`}>{team.name || "待定"}</div>
        {probability !== null && probability !== undefined ? <div className="text-xs text-paper/45">晋级概率 {formatProbability(probability)}</div> : null}
      </div>
      {isWinner ? <span className="rounded-full bg-gold px-2 py-1 text-[11px] font-semibold text-pitch">胜出</span> : null}
    </div>
  );
}

function ChampionCard({ champion }: { champion: NormalizedTeam }) {
  return (
    <div className="rounded-lg border border-gold/25 bg-gold/10 p-5 text-center">
      <div className="text-sm font-medium text-gold">冠军</div>
      <div className="mt-4 flex justify-center">
        <FlagBubble team={champion} highlighted />
      </div>
      <div className="mt-3 text-xl font-semibold">{champion.name || "等待真实冠军结果"}</div>
      <div className="mt-2 text-xs text-paper/50">有真实数据后自动显示，不会提前编造。</div>
    </div>
  );
}

function FlagBubble({ team, highlighted = false }: { team: NormalizedTeam; highlighted?: boolean }) {
  if (team.flagUrl) {
    return (
      <img
        src={team.flagUrl}
        alt={`${team.name || "球队"} 国旗`}
        className={`h-9 w-9 shrink-0 rounded-full border object-cover ${highlighted ? "border-gold shadow-[0_0_0_3px_rgba(232,179,60,0.18)]" : "border-white/20"}`}
      />
    );
  }

  return (
    <span
      className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full border bg-white/8 text-base ${highlighted ? "border-gold shadow-[0_0_0_3px_rgba(232,179,60,0.18)]" : "border-white/20"}`}
      aria-label={`${team.name || "球队"} 国旗`}
    >
      {team.flagText || initials(team.name)}
    </span>
  );
}

function EmptyBracketNode({ title }: { title: string }) {
  return (
    <div className="rounded-lg border border-dashed border-white/15 bg-pitch/52 p-4">
      <div className="text-sm font-semibold text-paper/75">{title}</div>
      <div className="mt-2 text-xs text-paper/45">数据不足，暂未生成</div>
    </div>
  );
}

type NormalizedRound = BracketRound & {
  key: string;
  title: string;
  matches: BracketMatch[];
};

type NormalizedTeam = {
  name: string;
  flagText?: string;
  flagUrl?: string;
};

function normalizeRounds(rounds: BracketRound[]): NormalizedRound[] {
  return rounds
    .map((round, index) => {
      const key = String(round.key || round.round || `round-${index}`);
      return {
        ...round,
        key,
        title: round.title || roundTitle(key),
        matches: Array.isArray(round.matches) ? round.matches : [],
      };
    })
    .filter((round) => round.matches.length > 0)
    .sort((left, right) => orderIndex(left.key) - orderIndex(right.key));
}

function orderIndex(key: string): number {
  const normalized = normalizeRoundKey(key);
  const index = roundOrder.indexOf(normalized);
  return index >= 0 ? index : 99;
}

function normalizeRoundKey(key: string): string {
  const lower = key.toLowerCase();
  if (lower.includes("16")) return "round16";
  if (lower.includes("quarter") || lower.includes("8")) return "quarterfinal";
  if (lower.includes("semi") || lower.includes("4")) return "semifinal";
  if (lower.includes("final")) return "final";
  if (lower.includes("champion")) return "champion";
  return lower;
}

function roundTitle(key: string): string {
  const normalized = normalizeRoundKey(key);
  if (normalized === "round16") return "十六强";
  if (normalized === "quarterfinal") return "四分之一决赛";
  if (normalized === "semifinal") return "半决赛";
  if (normalized === "final") return "决赛";
  if (normalized === "champion") return "冠军";
  return key;
}

function getTeam(value?: string | BracketTeam | null, fallbackFlag?: string): NormalizedTeam {
  if (!value) return { name: "", flagText: flagFromAny(fallbackFlag) };
  if (typeof value === "string") return { name: value, flagText: flagFromAny(fallbackFlag) };

  const name = String(value.name || value.team || "");
  const flagUrl = urlFlag(value.flag_url || value.flag);
  return {
    name,
    flagUrl,
    flagText: flagUrl ? undefined : flagFromAny(value.flag_emoji || value.flag || fallbackFlag || value.iso2 || value.country_code),
  };
}

function flagFromAny(value?: string | null): string | undefined {
  if (!value) return undefined;
  const trimmed = String(value).trim();
  if (!trimmed) return undefined;
  if (/^https?:\/\//i.test(trimmed)) return undefined;
  if (/^[A-Za-z]{2}$/.test(trimmed)) return isoFlag(trimmed);
  return trimmed;
}

function urlFlag(value?: string | null): string | undefined {
  if (!value) return undefined;
  const trimmed = String(value).trim();
  return /^https?:\/\//i.test(trimmed) ? trimmed : undefined;
}

function isoFlag(code: string): string {
  return code
    .toUpperCase()
    .split("")
    .map((letter) => String.fromCodePoint(127397 + letter.charCodeAt(0)))
    .join("");
}

function initials(value?: string): string {
  if (!value) return "待";
  return value.trim().slice(0, 2);
}

function formatProbability(value: string | number): string {
  const number = Number(value);
  if (!Number.isFinite(number)) return String(value);
  return formatPercent(number > 1 ? number / 100 : number);
}
