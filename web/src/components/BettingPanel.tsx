import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { BarChart3, Bot, Loader2, Ticket, X } from "lucide-react";
import { apiGet, apiPost } from "../api/client";
import type { Bet, Match, OddsSnapshot, Suggestion, UserProfile } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { formatDateTime, formatDecimal, formatMoney, playTypeLabel, selectionLabel } from "../utils/format";
import { hasCompleteResult } from "../utils/matchAnalytics";

const BETTING_ENABLED = import.meta.env.VITE_BETTING_ENABLED === "true";
const CUTOFF_MS = 5 * 60 * 1000;
const STAKE_PRESETS = ["1", "10", "50", "100"];

type BetTab = "had" | "correct_score" | "ai" | "analysis";

type BetOption = {
  matchId: string;
  matchLabel: string;
  playType: "had" | "correct_score";
  marketLabel: string;
  selection: string;
  selectionLabel: string;
  odds: number;
  snapshotId?: number;
};

type BettingPanelProps = {
  match: Match;
  suggestion?: Suggestion | null;
  compact?: boolean;
  showAi?: boolean;
  analysisTo?: string;
  onShowAnalysis?: () => void;
  className?: string;
};

export function BettingPanel({
  match,
  suggestion,
  compact = false,
  showAi = false,
  analysisTo,
  onShowAnalysis,
  className = "",
}: BettingPanelProps) {
  const [activeTab, setActiveTab] = useState<BetTab>("had");
  const [selected, setSelected] = useState<BetOption | null>(null);
  const status = useMemo(() => bettingStatus(match), [match]);
  const had = useMemo(() => latestOdds(match, "had"), [match]);
  const crs = useMemo(() => latestOdds(match, "crs"), [match]);
  const hadOptions = useMemo(() => buildHadOptions(match, had), [match, had]);
  const scoreGroups = useMemo(() => buildCorrectScoreGroups(match, crs), [match, crs]);
  const scoreCount = scoreGroups.home.length + scoreGroups.draw.length + scoreGroups.away.length;
  const canBet = status.key === "open";

  const tabs: Array<{ key: BetTab; label: string; visible: boolean }> = [
    { key: "had", label: "胜平负", visible: true },
    { key: "correct_score", label: "正确比分", visible: true },
    { key: "ai", label: "AI推荐", visible: showAi },
    { key: "analysis", label: "数据分析", visible: Boolean(analysisTo || onShowAnalysis) },
  ];

  return (
    <section className={`rounded-lg border border-white/10 bg-white/[0.06] p-4 ${className}`}>
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-2 text-sm font-semibold text-paper">
            <Ticket size={16} className="text-gold" />
            模拟投注
          </div>
          {!compact ? (
            <div className="mt-1 text-xs text-paper/50">{match.match_num || match.league} · {formatDateTime(match.kickoff_at)}</div>
          ) : null}
        </div>
        <span className={`w-fit rounded-full border px-3 py-1 text-xs font-semibold ${status.className}`}>{status.label}</span>
      </div>

      <div className="-mx-1 mt-4 flex gap-1 overflow-x-auto px-1 pb-1">
        {tabs.filter((tab) => tab.visible).map((tab) => (
          <button
            key={tab.key}
            type="button"
            onClick={() => {
              setActiveTab(tab.key);
              if (tab.key === "analysis" && onShowAnalysis) onShowAnalysis();
            }}
            className={`min-w-fit rounded-lg border px-3 py-2 text-xs font-semibold transition ${
              activeTab === tab.key ? "border-gold bg-gold text-pitch" : "border-white/12 text-paper/68 hover:border-gold/45"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className="mt-4">
        {activeTab === "had" ? (
          <OddsButtonGrid
            emptyText={had ? "暂无可用胜平负选项。" : "暂无胜平负赔率。"}
            options={hadOptions}
            canBet={canBet}
            disabledReason={status.label}
            onSelect={setSelected}
          />
        ) : null}

        {activeTab === "correct_score" ? (
          <CorrectScoreContent
            groups={scoreGroups}
            scoreCount={scoreCount}
            canBet={canBet}
            disabledReason={status.label}
            onSelect={setSelected}
          />
        ) : null}

        {activeTab === "ai" ? <AiSuggestion suggestion={suggestion} /> : null}

        {activeTab === "analysis" ? (
          <div className="rounded-lg border border-white/10 bg-pitch/55 p-4 text-sm text-paper/65">
            <div className="flex items-start gap-2">
              <BarChart3 size={16} className="mt-0.5 shrink-0 text-gold" />
              <div>展开模型概率、市场抽水、EV 信号和历史走势。这里只做研究展示，不是投注建议。</div>
            </div>
            {analysisTo ? (
              <Link to={analysisTo} className="mt-4 inline-flex rounded-lg border border-gold/40 px-3 py-2 text-sm font-semibold text-gold hover:bg-gold/10">
                查看分析
              </Link>
            ) : null}
          </div>
        ) : null}
      </div>

      {selected ? <BetConfirmModal option={selected} onClose={() => setSelected(null)} /> : null}
    </section>
  );
}

function OddsButtonGrid({
  options,
  canBet,
  disabledReason,
  emptyText,
  onSelect,
}: {
  options: BetOption[];
  canBet: boolean;
  disabledReason: string;
  emptyText: string;
  onSelect: (option: BetOption) => void;
}) {
  if (!options.length) return <div className="rounded-lg border border-white/10 p-4 text-sm text-paper/60">{emptyText}</div>;
  return (
    <div className="grid gap-2 sm:grid-cols-3">
      {options.map((option) => (
        <button
          key={`${option.playType}-${option.selection}`}
          type="button"
          onClick={() => onSelect(option)}
          disabled={!canBet}
          title={!canBet ? disabledReason : `${option.selectionLabel} ${formatDecimal(option.odds)}`}
          className="min-h-[74px] rounded-lg border border-white/10 bg-pitch/70 px-3 py-3 text-left transition hover:border-gold/55 hover:bg-pitch disabled:cursor-not-allowed disabled:opacity-55"
        >
          <div className="text-xs text-paper/55">{option.selectionLabel}</div>
          <div className="mt-1 text-xl font-semibold text-gold">{formatDecimal(option.odds)}</div>
        </button>
      ))}
    </div>
  );
}

function CorrectScoreContent({
  groups,
  scoreCount,
  canBet,
  disabledReason,
  onSelect,
}: {
  groups: ReturnType<typeof buildCorrectScoreGroups>;
  scoreCount: number;
  canBet: boolean;
  disabledReason: string;
  onSelect: (option: BetOption) => void;
}) {
  if (!scoreCount) {
    return (
      <div className="rounded-lg border border-white/10 bg-pitch/55 p-4">
        <div className="font-semibold text-paper">正确比分</div>
        <p className="mt-2 text-sm text-paper/60">当前暂无比分赔率，暂未开放。</p>
      </div>
    );
  }
  return (
    <div className="space-y-3">
      <ScoreGroup title="主胜" options={groups.home} canBet={canBet} disabledReason={disabledReason} onSelect={onSelect} />
      <ScoreGroup title="平局" options={groups.draw} canBet={canBet} disabledReason={disabledReason} onSelect={onSelect} />
      <ScoreGroup title="客胜" options={groups.away} canBet={canBet} disabledReason={disabledReason} onSelect={onSelect} />
    </div>
  );
}

function ScoreGroup({
  title,
  options,
  canBet,
  disabledReason,
  onSelect,
}: {
  title: string;
  options: BetOption[];
  canBet: boolean;
  disabledReason: string;
  onSelect: (option: BetOption) => void;
}) {
  if (!options.length) return null;
  return (
    <div>
      <div className="mb-2 text-xs font-semibold text-paper/55">{title}</div>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-4">
        {options.map((option) => (
          <button
            key={`${option.playType}-${option.selection}`}
            type="button"
            onClick={() => onSelect(option)}
            disabled={!canBet}
            title={!canBet ? disabledReason : `${option.selectionLabel} ${formatDecimal(option.odds)}`}
            className="rounded-lg border border-white/10 bg-pitch/70 px-3 py-2 text-left transition hover:border-gold/55 hover:bg-pitch disabled:cursor-not-allowed disabled:opacity-55"
          >
            <div className="text-sm font-semibold text-paper">{option.selectionLabel}</div>
            <div className="mt-1 text-base font-semibold text-gold">{formatDecimal(option.odds)}</div>
          </button>
        ))}
      </div>
    </div>
  );
}

function AiSuggestion({ suggestion }: { suggestion?: Suggestion | null }) {
  if (!suggestion) {
    return <div className="rounded-lg border border-white/10 p-4 text-sm text-paper/60">登录后查看 AI 观察结果。</div>;
  }
  if (!suggestion.play_type || !suggestion.selection) {
    return <div className="rounded-lg border border-white/10 p-4 text-sm text-paper/60">暂无可展示的 AI 观察信号。</div>;
  }
  return (
    <div className="rounded-lg border border-white/10 bg-pitch/55 p-4 text-sm">
      <div className="flex items-center gap-2 font-semibold">
        <Bot size={16} className="text-gold" />
        AI 观察
      </div>
      <div className="mt-3 text-paper/70">
        {playTypeLabel(suggestion.play_type)} · {selectionLabel(suggestion.selection)}
      </div>
      <div className="mt-2 text-paper/55">建议演示金额：{formatMoney(suggestion.suggested_stake)}</div>
      <div className="mt-2 text-xs text-paper/45">这是风险管理演示，不是盈利建议。</div>
    </div>
  );
}

function BetConfirmModal({ option, onClose }: { option: BetOption; onClose: () => void }) {
  const { token, isAuthenticated } = useAuth();
  const [stake, setStake] = useState("1");
  const [balance, setBalance] = useState<string | number | null>(null);
  const [message, setMessage] = useState("");
  const [result, setResult] = useState<Bet | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const estimate = Number(stake || 0) * Number(option.odds || 0);

  useEffect(() => {
    let cancelled = false;
    if (!token) {
      setBalance(null);
      return;
    }
    apiGet<UserProfile>("/me", token)
      .then((profile) => {
        if (!cancelled) setBalance(profile.balance);
      })
      .catch(() => {
        if (!cancelled) setBalance(null);
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  async function submit() {
    if (!token) {
      setMessage("请先登录后进行虚拟投注。");
      return;
    }
    try {
      setSubmitting(true);
      setMessage("");
      const response = await apiPost<Bet>(
        "/bets",
        {
          legs: [{ match_id: option.matchId, play_type: option.playType, selection: option.selection }],
          parlay: "single",
          stake: Number(stake),
        },
        token,
      );
      setResult(response);
      setBalance(response.balance ?? balance);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "虚拟投注提交失败");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end bg-black/55 px-3 py-4 backdrop-blur-sm sm:items-center sm:justify-center">
      <div className="w-full max-w-lg rounded-lg border border-white/12 bg-pitch p-5 shadow-2xl">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-xl font-semibold text-paper">投注确认</h2>
            <p className="mt-1 text-xs text-paper/50">虚拟资金模拟，不提供真实购彩服务。</p>
          </div>
          <button type="button" onClick={onClose} className="rounded p-1 text-paper/55 hover:bg-white/10 hover:text-paper" aria-label="关闭">
            <X size={18} />
          </button>
        </div>

        <div className="mt-4 space-y-2 rounded-lg border border-white/10 bg-white/[0.04] p-4 text-sm">
          <InfoRow label="比赛" value={option.matchLabel} />
          <InfoRow label="玩法" value={option.marketLabel} />
          <InfoRow label="选择" value={option.selectionLabel} />
          <InfoRow label="赔率" value={formatDecimal(option.odds)} highlight />
        </div>

        <div className="mt-4">
          <div className="text-sm font-semibold text-paper">投注金额</div>
          <div className="mt-2 grid grid-cols-4 gap-2">
            {STAKE_PRESETS.map((value) => (
              <button
                key={value}
                type="button"
                onClick={() => setStake(value)}
                className={`rounded-lg border px-3 py-2 text-sm font-semibold ${
                  stake === value ? "border-gold bg-gold text-pitch" : "border-white/12 text-paper/72 hover:border-gold/45"
                }`}
              >
                {value}
              </button>
            ))}
          </div>
          <input
            value={stake}
            onChange={(event) => setStake(event.target.value)}
            type="number"
            min="1"
            step="1"
            className="mt-3 w-full rounded-lg border border-white/10 bg-pitch/70 px-3 py-3 text-paper outline-none focus:border-gold/60"
          />
        </div>

        <div className="mt-4 grid gap-2 text-sm sm:grid-cols-2">
          <div className="rounded-lg bg-white/[0.05] p-3">
            <div className="text-paper/50">预计返还</div>
            <div className="mt-1 text-lg font-semibold text-gold">{formatMoney(estimate)}</div>
          </div>
          <div className="rounded-lg bg-white/[0.05] p-3">
            <div className="text-paper/50">当前余额</div>
            <div className="mt-1 text-lg font-semibold text-paper">{balance === null ? "登录后显示" : formatMoney(balance)}</div>
          </div>
        </div>

        {!isAuthenticated ? (
          <Link to="/auth" className="mt-4 block rounded-lg border border-gold/40 px-4 py-3 text-center text-sm font-semibold text-gold hover:bg-gold/10">
            登录 / 注册后提交
          </Link>
        ) : (
          <button
            type="button"
            onClick={submit}
            disabled={submitting || Number(stake) <= 0}
            className="mt-4 flex w-full items-center justify-center gap-2 rounded-lg bg-gold px-4 py-3 font-semibold text-pitch disabled:cursor-not-allowed disabled:opacity-55"
          >
            {submitting ? <Loader2 size={16} className="animate-spin" /> : null}
            {submitting ? "提交中" : "确认投注"}
          </button>
        )}
        <button type="button" onClick={onClose} className="mt-2 w-full rounded-lg border border-white/10 px-4 py-3 text-sm text-paper/65 hover:bg-white/10">
          取消
        </button>

        {message ? <div className="mt-4 rounded-lg border border-danger/40 bg-danger/10 p-3 text-sm text-paper">{message}</div> : null}
        {result ? (
          <div className="mt-4 rounded-lg border border-gold/40 bg-gold/10 p-3 text-sm text-paper">
            <div className="font-semibold text-gold">投注单 #{result.id} 已创建</div>
            <div className="mt-2 grid gap-1 text-paper/75">
              <span>投注金额：{formatMoney(result.stake)}</span>
              <span>赔率：{formatDecimal(option.odds)}</span>
              <span>预计返还：{formatMoney(result.potential_payout)}</span>
              <span>当前状态：{result.status}</span>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function InfoRow({ label, value, highlight = false }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-paper/50">{label}</span>
      <span className={`text-right font-semibold ${highlight ? "text-gold" : "text-paper"}`}>{value}</span>
    </div>
  );
}

function latestOdds(match: Match, playType: string): OddsSnapshot | undefined {
  return match.latest_odds?.find((row) => row.play_type === playType);
}

function buildHadOptions(match: Match, snapshot?: OddsSnapshot): BetOption[] {
  if (!snapshot?.odds) return [];
  return [
    { key: "3", label: `${match.home_team}胜` },
    { key: "1", label: "平局" },
    { key: "0", label: `${match.away_team}胜` },
  ].flatMap((item) => {
    const odds = snapshot.odds[item.key];
    if (odds === undefined || odds === null) return [];
    return [
      {
        matchId: match.match_id,
        matchLabel: `${match.home_team} vs ${match.away_team}`,
        playType: "had" as const,
        marketLabel: "胜平负",
        selection: item.key,
        selectionLabel: item.label,
        odds: Number(odds),
        snapshotId: snapshot.id,
      },
    ];
  });
}

function buildCorrectScoreGroups(match: Match, snapshot?: OddsSnapshot) {
  const groups: { home: BetOption[]; draw: BetOption[]; away: BetOption[] } = { home: [], draw: [], away: [] };
  if (!snapshot?.odds) return groups;
  for (const [rawSelection, rawOdds] of Object.entries(snapshot.odds)) {
    const parsed = parseScoreSelection(rawSelection);
    const option: BetOption = {
      matchId: match.match_id,
      matchLabel: `${match.home_team} vs ${match.away_team}`,
      playType: "correct_score",
      marketLabel: "正确比分",
      selection: parsed.apiSelection,
      selectionLabel: parsed.label,
      odds: Number(rawOdds),
      snapshotId: snapshot.id,
    };
    groups[parsed.group].push(option);
  }
  for (const key of Object.keys(groups) as Array<keyof typeof groups>) {
    groups[key].sort((left, right) => scoreSortValue(left.selectionLabel) - scoreSortValue(right.selectionLabel));
  }
  return groups;
}

function parseScoreSelection(selection: string): { group: "home" | "draw" | "away"; apiSelection: string; label: string } {
  if (selection.includes("胜其")) return { group: "home", apiSelection: "other_home_win", label: "其他主胜" };
  if (selection.includes("平其")) return { group: "draw", apiSelection: "other_draw", label: "其他平局" };
  if (selection.includes("负其")) return { group: "away", apiSelection: "other_away_win", label: "其他客胜" };
  const [homeText, awayText] = selection.split(":");
  const home = Number(homeText);
  const away = Number(awayText);
  const group = home > away ? "home" : home === away ? "draw" : "away";
  return { group, apiSelection: `${home}-${away}`, label: `${home}-${away}` };
}

function scoreSortValue(label: string): number {
  if (label.startsWith("其他")) return 999;
  const [homeText, awayText] = label.split("-");
  return Number(homeText) * 10 + Number(awayText);
}

function bettingStatus(match: Match): { key: string; label: string; className: string } {
  if (!BETTING_ENABLED) return { key: "disabled", label: "投注未开启", className: "border-white/15 text-paper/55" };
  if (hasCompleteResult(match) || ["finished", "completed"].includes(match.status)) {
    return { key: "finished", label: "已完赛", className: "border-white/15 text-paper/55" };
  }
  if (match.status === "no_market") return { key: "no_market", label: "未开售", className: "border-white/15 text-paper/55" };
  if (match.status === "closed") return { key: "closed", label: "已截止", className: "border-danger/40 text-danger" };
  const kickoff = new Date(match.kickoff_at).getTime();
  const now = Date.now();
  if (kickoff <= now) return { key: "started", label: "已开赛", className: "border-danger/40 text-danger" };
  if (kickoff - now < CUTOFF_MS) return { key: "cutoff", label: "已截止", className: "border-danger/40 text-danger" };
  if (!latestOdds(match, "had") && !latestOdds(match, "crs")) {
    return { key: "no_odds", label: "暂无赔率", className: "border-white/15 text-paper/55" };
  }
  return { key: "open", label: "可投注", className: "border-gold/50 text-gold" };
}
