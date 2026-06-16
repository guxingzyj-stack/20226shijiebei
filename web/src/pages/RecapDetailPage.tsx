import { type ReactNode, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { AlertTriangle, ArrowLeft, BarChart3, CheckCircle2, FileText, ShieldCheck } from "lucide-react";
import { apiGet } from "../api/client";
import type { MatchRecap, MatchRecapResponse } from "../api/types";
import { InfoTip } from "../components/InfoTip";
import { MetricHelp } from "../components/MetricHelp";
import { evValueGuide, type GlossaryKey } from "../recaps/glossary";
import { aggregateEvSignals, evResultText } from "../recaps/recapUtils";
import { formatDateTime, formatDecimal, formatPercent, playTypeLabel, selectionLabel } from "../utils/format";

const outcomeLabel: Record<string, string> = {
  home: "主胜",
  draw: "平局",
  away: "客胜",
};

type RecapEvRow = MatchRecap["ev"]["signals"][number] & {
  match_label?: string;
  occurrence_count: number;
};

export function RecapDetailPage() {
  const { matchId = "" } = useParams();
  const [response, setResponse] = useState<MatchRecapResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showAllEv, setShowAllEv] = useState(false);
  const [showDetails, setShowDetails] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        setLoading(true);
        const result = await apiGet<MatchRecapResponse>(`/recaps/matches/${encodeURIComponent(matchId)}`);
        if (!cancelled) setResponse(result);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "复盘详情加载失败");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [matchId]);

  useEffect(() => {
    setShowAllEv(false);
    setShowDetails(false);
  }, [matchId]);

  const recap = response?.recap ?? null;
  const evRows = useMemo(
    () =>
      recap
        ? aggregateEvSignals(
            recap.ev.signals.map((signal) => ({
              ...signal,
              match_id: recap.match_id,
              match_label: `${recap.home_team} vs ${recap.away_team}`,
            })),
          )
        : [],
    [recap],
  );
  const visibleEvRows = showAllEv ? evRows : evRows.slice(0, 20);

  if (loading) return <div className="rounded-lg border border-white/10 p-5 text-paper/65">复盘详情加载中...</div>;
  if (error) return <div className="rounded-lg border border-danger/40 bg-danger/10 p-4 text-sm">{error}</div>;
  if (!response?.available || !recap) {
    return (
      <div className="space-y-4">
        <Link to="/recaps" className="inline-flex items-center gap-2 text-sm text-paper/60 hover:text-gold">
          <ArrowLeft size={16} /> 返回复盘列表
        </Link>
        <section className="rounded-lg border border-white/10 bg-white/[0.05] p-6">
          <h1 className="text-xl font-semibold">赛后复盘暂不可用</h1>
          <p className="mt-3 text-sm text-paper/62">{reasonText(response?.reason)}</p>
        </section>
      </div>
    );
  }

  const shouldShowSettlement = hasPublicSettlement(recap);
  const marketHit = recap.three_way_summary?.market_hit ?? (recap.market.favorite ? recap.market.favorite === recap.result.winner : null);
  const modelHit = recap.three_way_summary?.model_hit ?? recap.model.prediction_correct;
  const heroTitle = recap.summary.title_cn || fallbackTitleCn(recap);
  const threeWayText = recap.three_way_summary?.text || fallbackThreeWayText(recap, marketHit, modelHit);

  return (
    <div className="space-y-5">
      <Link to="/recaps" className="inline-flex items-center gap-2 text-sm text-paper/60 hover:text-gold">
        <ArrowLeft size={16} /> 返回复盘列表
      </Link>

      <section className="rounded-lg border border-gold/20 bg-white/[0.06] p-5 shadow-soft">
        <p className="text-sm text-paper/50">
          {recap.match_num || recap.match_id} · {formatDateTime(recap.kickoff_at)} · {recap.status}
        </p>
        <div className="mt-4 grid gap-4 lg:grid-cols-[1fr_auto_1fr] lg:items-center">
          <TeamScore name={recap.home_team} score={recap.result.home} align="left" />
          <div className="text-center text-xs uppercase tracking-[0.25em] text-paper/40">FT</div>
          <TeamScore name={recap.away_team} score={recap.result.away} align="right" />
        </div>
        <h1 className="mt-5 text-xl font-semibold leading-relaxed text-paper md:text-2xl">{heroTitle}</h1>
        {threeWayText ? (
          <p className="mt-3 rounded-lg border border-white/10 bg-pitch/55 p-3 text-sm leading-6 text-paper/70">
            {threeWayText}
          </p>
        ) : null}
      </section>

      <section className="grid gap-4 lg:grid-cols-3">
        <StoryCard
          title="市场赛前怎么看"
          eyebrow="赔率倾向"
          value={recap.market.favorite ? outcomeLabel[recap.market.favorite] : "暂无数据"}
          result={hitText(marketHit)}
          helpKey="marketFavorite"
        >
          收盘赔率最低的一方，就是市场更看好的方向。
        </StoryCard>
        <StoryCard
          title="模型赛前怎么看"
          eyebrow="模型判断"
          value={recap.model.predicted_outcome ? outcomeLabel[recap.model.predicted_outcome] : "无预测"}
          result={hitText(modelHit)}
          helpKey="modelPrediction"
        >
          这里只看赛前概率最大的胜平负方向，不做赛后倒推。
        </StoryCard>
        <StoryCard
          title="剧本当时怎么说"
          eyebrow={scriptTypeText(recap)}
          value={recap.script?.has_script ? recap.script.script_score || "有剧本" : "暂无剧本"}
          result={scriptResultText(recap)}
          helpKey="researchSignal"
        >
          剧本是商业推演素材，只能拿来对照现实，不是预测依据。
        </StoryCard>
      </section>

      <ScriptStory recap={recap} />

      <section className="rounded-lg border border-white/10 bg-white/[0.05] p-4">
        <button
          type="button"
          onClick={() => setShowDetails((value) => !value)}
          className="flex w-full items-center justify-between gap-4 text-left"
        >
          <span>
            <span className="block text-lg font-semibold">详细数据</span>
            <span className="mt-1 block text-sm text-paper/55">赔率、隐含概率、模型概率、EV 明细等专业数据默认收起。</span>
          </span>
          <span className="rounded-lg border border-gold/45 px-3 py-2 text-sm text-gold">
            {showDetails ? "收起详细数据" : "查看详细数据"}
          </span>
        </button>
        {showDetails ? (
          <div className="mt-5 space-y-4">
            <section className="grid gap-4 xl:grid-cols-3">
              <Panel title="市场赔率倾向" icon={BarChart3} helpKey="had">
                <OddsRow title="HAD 开盘赔率" odds={recap.market.had_open} helpKey="openingOdds" />
                <OddsRow title="HAD 收盘赔率" odds={recap.market.had_close} helpKey="closingOdds" />
                <div className="mt-4 grid grid-cols-3 gap-2">
                  {["home", "draw", "away"].map((key) => (
                    <Metric key={key} label={`${outcomeLabel[key]}隐含概率`} value={formatPercent(recap.market.close_implied_probabilities[key])} helpKey="impliedProbability" />
                  ))}
                </div>
              </Panel>

              <Panel title="模型预测" icon={ShieldCheck} helpKey="modelPrediction">
                <div className="grid gap-2">
                  <Metric label="model_version" value={recap.model.model_version ?? "无"} helpKey="modelVersion" />
                  <Metric label="预测方向" value={recap.model.predicted_outcome ? outcomeLabel[recap.model.predicted_outcome] : "无预测"} />
                  <Metric label="置信度" value={formatPercent(recap.model.confidence)} />
                  <Metric label="是否命中" value={predictionText(recap.model.prediction_correct)} helpKey="modelHit" />
                </div>
                <div className="mt-4 grid grid-cols-3 gap-2">
                  {["home", "draw", "away"].map((key) => (
                    <Metric key={key} label={outcomeLabel[key]} value={formatPercent(recap.model.probs[key])} />
                  ))}
                </div>
              </Panel>

              <Panel title="EV 信号复盘" icon={AlertTriangle} helpKey="evSignal">
                <div className="grid grid-cols-2 gap-2">
                  <Metric label="信号总数" value={recap.ev.total_ev_signals} helpKey="evSignal" />
                  <Metric label="研究信号" value={recap.ev.research_only_count} helpKey="researchOnly" />
                  <Metric label="候选信号" value={recap.ev.suggestion_eligible_count} helpKey="suggestionEligible" />
                  <Metric label="命中 / 复盘未命中" value={`${recap.ev.hit_count} / ${recap.ev.miss_count}`} helpKey="evMiss" />
                </div>
                <p className="mt-4 rounded-lg border border-gold/25 bg-gold/10 p-3 text-xs leading-5 text-paper/68">
                  EV 区域仅用于赛后研究复盘，不是投注建议。
                </p>
              </Panel>
            </section>

            <Panel title="EV 明细" icon={BarChart3} helpKey="ev">
              <EvTable evRows={evRows} visibleEvRows={visibleEvRows} showAllEv={showAllEv} onToggle={() => setShowAllEv((value) => !value)} />
            </Panel>

            {shouldShowSettlement ? (
              <Panel title="结算状态" icon={ShieldCheck} helpKey="noPublicBets">
                <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                  <Metric label="settled_bets" value={recap.settlement.settled_bets} helpKey="settledBets" />
                  <Metric label="won_bets" value={recap.settlement.won_bets} helpKey="wonBets" />
                  <Metric label="lost_bets" value={recap.settlement.lost_bets} helpKey="lostBets" />
                  <Metric label="void_bets" value={recap.settlement.void_bets} helpKey="voidBets" />
                  <Metric label="open_bets" value={recap.settlement.open_bets} helpKey="openBets" />
                  <Metric label="状态" value={recap.settlement.settlement_status} />
                </div>
              </Panel>
            ) : null}

            <Panel title="技术摘要" icon={CheckCircle2}>
              <h2 className="text-lg font-semibold text-paper">{recap.summary.title}</h2>
              <ul className="mt-4 space-y-2 text-sm leading-6 text-paper/68">
                {recap.summary.bullets.map((bullet) => (
                  <li key={bullet} className="flex gap-2">
                    <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-gold" />
                    <span>{bullet}</span>
                  </li>
                ))}
              </ul>
            </Panel>
          </div>
        ) : null}
      </section>
    </div>
  );
}

function TeamScore({ name, score, align }: { name: string; score: number; align: "left" | "right" }) {
  return (
    <div className={align === "right" ? "text-left lg:text-right" : "text-left"}>
      <div className="text-lg font-semibold md:text-2xl">{name}</div>
      <div className="mt-2 text-5xl font-bold text-gold md:text-6xl">{score}</div>
    </div>
  );
}

function StoryCard({
  title,
  eyebrow,
  value,
  result,
  children,
  helpKey,
}: {
  title: string;
  eyebrow: string;
  value: ReactNode;
  result: string;
  children: ReactNode;
  helpKey?: GlossaryKey;
}) {
  return (
    <section className="rounded-lg border border-white/10 bg-white/[0.055] p-5">
      <div className="flex items-center justify-between gap-3">
        <span className="text-xs uppercase tracking-[0.18em] text-gold">{eyebrow}</span>
        <InfoTip glossaryKey={helpKey} label={title} />
      </div>
      <h2 className="mt-3 text-lg font-semibold">{title}</h2>
      <div className="mt-4 flex items-end justify-between gap-3">
        <div className="text-2xl font-bold text-paper">{value}</div>
        <span className="rounded-full border border-white/10 bg-pitch/60 px-3 py-1 text-xs text-paper/70">{result}</span>
      </div>
      <p className="mt-4 text-sm leading-6 text-paper/62">{children}</p>
    </section>
  );
}

function ScriptStory({ recap }: { recap: MatchRecap }) {
  const script = recap.script;
  const realScore = `${recap.result.home}:${recap.result.away}`;
  return (
    <section className="rounded-lg border border-gold/30 bg-[#10283b] p-5 shadow-soft">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <div className="flex items-center gap-2 text-lg font-semibold text-gold">
            <FileText size={18} /> 剧本对照：花絮 · 反面教材
          </div>
          <p className="mt-2 text-sm leading-6 text-paper/70">
            这是商业剧本推演，不是预测。真实足球只服从概率，不服从剧本。
          </p>
        </div>
        <Link to={scriptDeepLink(recap)} className="text-sm text-gold hover:text-gold/80">
          去剧本页 →
        </Link>
      </div>

      {!script?.has_script ? (
        <p className="mt-5 rounded-lg border border-white/10 bg-black/15 p-4 text-sm text-paper/70">本场暂无剧本预言。</p>
      ) : (
        <div className="mt-5 grid gap-4 md:grid-cols-2">
          <div className="rounded-lg border border-white/10 bg-black/15 p-4">
            <div className="text-xs text-paper/45">剧本当时说</div>
            <p className="mt-2 text-lg font-semibold">
              {recap.home_team} {script.script_score} {recap.away_team}
            </p>
            {script.narrative ? <p className="mt-3 text-sm leading-6 text-paper/66">“{script.narrative}”</p> : null}
          </div>
          <div className="rounded-lg border border-gold/25 bg-gold/10 p-4">
            <div className="text-xs text-paper/45">真实结果</div>
            <p className="mt-2 text-lg font-semibold">
              {recap.home_team} {realScore} {recap.away_team}
            </p>
            <div className="mt-3 inline-flex rounded-full border border-gold/35 px-3 py-1 text-xs text-gold">
              {script.is_real ? "已知赛果样本" : script.exact_hit ? "比分命中" : script.direction_hit ? "方向命中" : "剧本崩了"}
            </div>
            <p className="mt-3 text-sm leading-6 text-paper/70">
              {script.is_real ? "这场是已踢真实比分标注，不计入剧本预测能力。" : script.comment || "剧本只用于赛后娱乐对照。"}
            </p>
          </div>
        </div>
      )}
    </section>
  );
}

function EvTable({
  evRows,
  visibleEvRows,
  showAllEv,
  onToggle,
}: {
  evRows: RecapEvRow[];
  visibleEvRows: RecapEvRow[];
  showAllEv: boolean;
  onToggle: () => void;
}) {
  if (!evRows.length) return <p className="text-sm text-paper/60">暂无 EV 信号。</p>;
  return (
    <div>
      <div className="mb-3 flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
        <p className="text-xs text-paper/50">默认展示 Top 20，按 EV 从高到低排序，并聚合重复信号。</p>
        {evRows.length > 20 ? (
          <button
            type="button"
            onClick={onToggle}
            className="inline-flex items-center justify-center rounded-lg border border-gold/45 px-3 py-2 text-sm text-gold transition hover:bg-gold/10"
          >
            {showAllEv ? "收起" : `展开全部 ${evRows.length} 条聚合信号`}
          </button>
        ) : null}
      </div>
      <div className="overflow-x-auto">
        <table className="mobile-card-table w-full text-sm sm:min-w-[780px]">
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
              <th>出现次数</th>
              <th>结果</th>
              <th>标记</th>
            </tr>
          </thead>
          <tbody>
            {visibleEvRows.map((signal, index) => (
              <tr key={`${signal.play_type}-${signal.selection}-${signal.model_version}-${index}`} className="border-t border-white/10">
                <td data-label="玩法" className="py-2">
                  {playTypeLabel(signal.play_type)}
                </td>
                <td data-label="选项">{selectionLabel(signal.selection)}</td>
                <td data-label="模型概率">{formatPercent(signal.model_prob)}</td>
                <td data-label="赔率">{formatDecimal(signal.odds)}</td>
                <td data-label="EV" className={Number(signal.ev || 0) > 0 ? "text-lg font-semibold text-gold sm:text-sm" : "text-paper/65"}>
                  {formatDecimal(signal.ev, 3)}
                </td>
                <td data-label="出现次数">{signal.occurrence_count > 1 ? `出现次数 x ${signal.occurrence_count}` : "1"}</td>
                <td data-label="结果">{evResultText(signal.hit)}</td>
                <td data-label="标记">{signal.research_only ? "研究信号，不是投注建议" : "观察信号"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-3">
        <MetricHelp title={evValueGuide.title}>
          EV 越高，说明模型和市场分歧越大；但 EV 不是中奖概率，也不是投注建议。{evValueGuide.scoreRisk}
        </MetricHelp>
      </div>
    </div>
  );
}

function Panel({ title, icon: Icon, children, helpKey }: { title: string; icon: typeof BarChart3; children: ReactNode; helpKey?: GlossaryKey }) {
  return (
    <section className="rounded-lg border border-white/10 bg-white/[0.055] p-5">
      <div className="mb-4 flex items-center gap-2 text-lg font-semibold">
        <Icon size={18} className="text-gold" />
        {title}
        <InfoTip glossaryKey={helpKey} label={title} />
      </div>
      {children}
    </section>
  );
}

function OddsRow({ title, odds, helpKey }: { title: string; odds: Record<string, number>; helpKey?: GlossaryKey }) {
  return (
    <div className="mt-3">
      <div className="text-xs text-paper/45">
        {title}
        <InfoTip glossaryKey={helpKey} label={title} />
      </div>
      <div className="mt-2 grid grid-cols-3 gap-2">
        {["3", "1", "0"].map((key) => (
          <Metric key={key} label={selectionLabel(key)} value={odds[key] ? formatDecimal(odds[key]) : "无"} helpKey="odds" />
        ))}
      </div>
    </div>
  );
}

function Metric({ label, value, helpKey }: { label: string; value: ReactNode; helpKey?: GlossaryKey }) {
  return (
    <div className="rounded-lg border border-white/10 bg-pitch/62 px-3 py-2">
      <div className="text-xs text-paper/45">
        {label}
        <InfoTip glossaryKey={helpKey} label={label} />
      </div>
      <div className="mt-1 text-sm font-semibold text-paper">{value}</div>
    </div>
  );
}

function hitText(value: boolean | null | undefined): string {
  if (value === true) return "说中了";
  if (value === false) return "没说中";
  return "不可判断";
}

function scriptTypeText(recap: MatchRecap): string {
  if (!recap.script?.has_script) return "无剧本";
  if (recap.script.is_real) return "已知赛果样本";
  return "剧本推演";
}

function scriptResultText(recap: MatchRecap): string {
  const script = recap.script;
  if (!script?.has_script) return "无对照";
  if (script.is_real) return "不计入预测能力";
  if (script.exact_hit) return "比分命中";
  if (script.direction_hit) return "方向命中";
  return "剧本崩了";
}

function scriptDeepLink(recap: MatchRecap): string {
  const params = new URLSearchParams();
  if (recap.script?.group) params.set("group", recap.script.group);
  params.set("team", `${recap.home_team}-${recap.away_team}`);
  return `/script?${params.toString()}`;
}

function fallbackTitleCn(recap: MatchRecap): string {
  const winner = recap.result.winner;
  const marketPick = recap.market.favorite;
  const modelPick = recap.model.predicted_outcome;
  if (winner === "draw" && marketPick === modelPick && (marketPick === "home" || marketPick === "away")) {
    const team = marketPick === "home" ? recap.home_team : recap.away_team;
    return `这场打平了。赛前市场和模型都看好${team}赢，结果都没说中。`;
  }
  if (winner === "home" && modelPick === "home") return `${recap.home_team}赢了，模型说中了方向。`;
  if (winner === "away" && modelPick === "away") return `${recap.away_team}赢了，模型说中了方向。`;
  if ((winner === "home" || winner === "away") && marketPick && modelPick && marketPick !== winner && modelPick !== winner) {
    return `爆了个冷门——${winnerTeamName(recap)}赢球，赛前市场和模型都没看到。`;
  }
  if (marketPick === winner && modelPick !== winner) return "市场方向说中了，模型这次没跟上。";
  if (modelPick === winner && marketPick !== winner) return "模型方向说中了，市场这次看错了。";
  return "这场比赛已经结束，赛前判断和真实结果可以放在一起复盘。";
}

function fallbackThreeWayText(recap: MatchRecap, marketHit: boolean | null, modelHit: boolean | null): string {
  let core = "这场适合把赛前判断和真实结果放在一起复盘。";
  if (marketHit === true && modelHit === true) core = "市场和模型都说中了方向。";
  else if (marketHit === true && modelHit === false) core = "市场方向说中了，模型这次没跟上。";
  else if (marketHit === false && modelHit === true) core = "模型方向说中了，市场这次看错了。";
  else if (marketHit === false && modelHit === false) {
    core = recap.result.winner === "draw" ? "真实结果是平局，市场和模型都没说中。" : `爆了个冷门，${winnerTeamName(recap)}赢球，赛前市场和模型都没看到。`;
  }

  const script = recap.script;
  if (!script?.has_script) return `${core}本场暂无剧本预言。`;
  if (script.is_real) return `${core}剧本为已知赛果样本，不计入预测能力。`;
  if (script.exact_hit) return `${core}剧本比分命中，但这只作为复盘观察。`;
  if (script.direction_hit) return `${core}剧本方向命中，比分没中。`;
  return `${core}剧本这次被现实打脸。`;
}

function winnerTeamName(recap: MatchRecap): string {
  if (recap.result.winner === "home") return recap.home_team;
  if (recap.result.winner === "away") return recap.away_team;
  return "双方";
}

function predictionText(value: boolean | null): string {
  if (value === true) return "命中";
  if (value === false) return "复盘未命中";
  return "无预测";
}

function hasPublicSettlement(recap: MatchRecap): boolean {
  if (recap.settlement.settlement_status !== "no_public_bets") return true;
  return (
    recap.settlement.settled_bets > 0 ||
    recap.settlement.won_bets > 0 ||
    recap.settlement.lost_bets > 0 ||
    recap.settlement.void_bets > 0 ||
    recap.settlement.open_bets > 0
  );
}

function reasonText(reason?: string): string {
  if (reason === "match_not_finished_or_result_missing") return "比赛尚未完赛，或赛果尚未回填。";
  if (reason === "match_not_found") return "未找到这场比赛。";
  return "复盘将在比赛结束并回填赛果后生成。";
}
