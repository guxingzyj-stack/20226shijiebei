import { type ReactNode, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { AlertTriangle, ArrowLeft, BarChart3, CheckCircle2, CircleSlash, ShieldCheck } from "lucide-react";
import { apiGet } from "../api/client";
import type { MatchRecap, MatchRecapResponse } from "../api/types";
import { formatDateTime, formatDecimal, formatPercent, playTypeLabel, selectionLabel } from "../utils/format";

const outcomeLabel: Record<string, string> = {
  home: "主胜",
  draw: "平局",
  away: "客胜",
};

export function RecapDetailPage() {
  const { matchId = "" } = useParams();
  const [response, setResponse] = useState<MatchRecapResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

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

  if (loading) return <div className="rounded-lg border border-white/10 p-5 text-paper/65">复盘详情加载中</div>;
  if (error) return <div className="rounded-lg border border-danger/40 bg-danger/10 p-4 text-sm">{error}</div>;
  if (!response?.available || !response.recap) {
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

  const recap = response.recap;

  return (
    <div className="space-y-5">
      <Link to="/recaps" className="inline-flex items-center gap-2 text-sm text-paper/60 hover:text-gold">
        <ArrowLeft size={16} /> 返回复盘列表
      </Link>

      <section className="rounded-lg border border-white/10 bg-white/[0.06] p-5 shadow-soft">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="text-sm text-paper/50">
              {recap.match_num || recap.match_id} · {formatDateTime(recap.kickoff_at)} · {recap.status}
            </p>
            <h1 className="mt-2 text-2xl font-semibold md:text-3xl">
              {recap.home_team} <span className="text-gold">{recap.result.scoreline}</span> {recap.away_team}
            </h1>
          </div>
          <StatusPill correct={recap.model.prediction_correct} />
        </div>
      </section>

      <section className="grid gap-4 xl:grid-cols-3">
        <Panel title="市场赔率倾向" icon={BarChart3}>
          <OddsRow title="HAD 开盘赔率" odds={recap.market.had_open} />
          <OddsRow title="HAD 收盘赔率" odds={recap.market.had_close} />
          <div className="mt-4 grid grid-cols-3 gap-2">
            {["home", "draw", "away"].map((key) => (
              <Metric key={key} label={`${outcomeLabel[key]}隐含概率`} value={formatPercent(recap.market.close_implied_probabilities[key])} />
            ))}
          </div>
          <div className="mt-4 grid gap-2 md:grid-cols-2">
            <Metric label="市场热门方向" value={outcomeLabel[recap.market.favorite || ""] || "暂无"} />
            <Metric label="市场判断结果" value={recap.market.favorite ? (recap.market.favorite === recap.result.winner ? "命中" : "未命中") : "不可判断"} />
          </div>
        </Panel>

        <Panel title="模型预测" icon={ShieldCheck}>
          <div className="grid gap-2">
            <Metric label="model_version" value={recap.model.model_version ?? "无"} />
            <Metric label="预测方向" value={outcomeLabel[recap.model.predicted_outcome || ""] || "无预测"} />
            <Metric label="置信度" value={formatPercent(recap.model.confidence)} />
            <Metric label="是否命中" value={predictionText(recap.model.prediction_correct)} />
          </div>
          <div className="mt-4 grid grid-cols-3 gap-2">
            {["home", "draw", "away"].map((key) => (
              <Metric key={key} label={outcomeLabel[key]} value={formatPercent(recap.model.probs[key])} />
            ))}
          </div>
        </Panel>

        <Panel title="EV 信号复盘" icon={AlertTriangle}>
          <div className="grid grid-cols-2 gap-2">
            <Metric label="信号总数" value={recap.ev.total_ev_signals} />
            <Metric label="研究信号" value={recap.ev.research_only_count} />
            <Metric label="候选信号" value={recap.ev.suggestion_eligible_count} />
            <Metric label="命中 / 未中" value={`${recap.ev.hit_count} / ${recap.ev.miss_count}`} />
          </div>
          <p className="mt-4 rounded-lg border border-gold/25 bg-gold/10 p-3 text-xs leading-5 text-paper/68">
            EV 区域仅用于赛后研究复盘，不是投注建议。
          </p>
        </Panel>
      </section>

      <section className="grid gap-4 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,0.9fr)]">
        <Panel title="EV 明细" icon={BarChart3}>
          {recap.ev.signals.length ? (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[720px] text-sm">
                <thead className="text-left text-paper/45">
                  <tr>
                    <th className="py-2">玩法</th>
                    <th>选项</th>
                    <th>模型概率</th>
                    <th>赔率</th>
                    <th>EV</th>
                    <th>结果</th>
                    <th>标记</th>
                  </tr>
                </thead>
                <tbody>
                  {recap.ev.signals.slice(0, 20).map((signal) => (
                    <tr key={`${signal.play_type}-${signal.selection}-${signal.model_version}`} className="border-t border-white/10">
                      <td className="py-2">{playTypeLabel(signal.play_type)}</td>
                      <td>{selectionLabel(signal.selection)}</td>
                      <td>{formatPercent(signal.model_prob)}</td>
                      <td>{formatDecimal(signal.odds)}</td>
                      <td className={Number(signal.ev || 0) > 0 ? "text-gold" : "text-paper/65"}>{formatDecimal(signal.ev, 3)}</td>
                      <td>{signal.hit === true ? "命中" : signal.hit === false ? "未中" : "不可判定"}</td>
                      <td>{signal.research_only ? "研究信号" : "观察信号"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-sm text-paper/60">暂无 EV 信号。</p>
          )}
        </Panel>

        <div className="space-y-4">
          <Panel title="结算状态" icon={ShieldCheck}>
            <div className="grid grid-cols-2 gap-2">
              <Metric label="settled_bets" value={recap.settlement.settled_bets} />
              <Metric label="won_bets" value={recap.settlement.won_bets} />
              <Metric label="lost_bets" value={recap.settlement.lost_bets} />
              <Metric label="void_bets" value={recap.settlement.void_bets} />
              <Metric label="open_bets" value={recap.settlement.open_bets} />
              <Metric label="状态" value={recap.settlement.settlement_status === "no_public_bets" ? "无公开注单" : recap.settlement.settlement_status} />
            </div>
          </Panel>

          <Panel title="数据质量" icon={CircleSlash}>
            <Quality recap={recap} />
          </Panel>
        </div>
      </section>

      <Panel title="复盘摘要" icon={CheckCircle2}>
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
  );
}

function Panel({ title, icon: Icon, children }: { title: string; icon: typeof BarChart3; children: ReactNode }) {
  return (
    <section className="rounded-lg border border-white/10 bg-white/[0.055] p-5">
      <div className="mb-4 flex items-center gap-2 text-lg font-semibold">
        <Icon size={18} className="text-gold" />
        {title}
      </div>
      {children}
    </section>
  );
}

function OddsRow({ title, odds }: { title: string; odds: Record<string, number> }) {
  return (
    <div className="mt-3">
      <div className="text-xs text-paper/45">{title}</div>
      <div className="mt-2 grid grid-cols-3 gap-2">
        {["3", "1", "0"].map((key) => (
          <Metric key={key} label={selectionLabel(key)} value={odds[key] ? formatDecimal(odds[key]) : "无"} />
        ))}
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="rounded-lg border border-white/10 bg-pitch/62 px-3 py-2">
      <div className="text-xs text-paper/45">{label}</div>
      <div className="mt-1 text-sm font-semibold text-paper">{value}</div>
    </div>
  );
}

function Quality({ recap }: { recap: MatchRecap }) {
  const rows = [
    ["has_result", recap.data_quality.has_result],
    ["has_had_odds", recap.data_quality.has_had_odds],
    ["has_prediction", recap.data_quality.has_prediction],
    ["has_ev_signal", recap.data_quality.has_ev_signal],
    ["has_settlement", recap.data_quality.has_settlement],
  ] as const;
  return (
    <div className="space-y-2">
      {rows.map(([label, value]) => (
        <div key={label} className="flex items-center justify-between rounded-md bg-pitch/55 px-3 py-2 text-sm">
          <span className="text-paper/58">{label}</span>
          <span className={value ? "text-emerald-100" : "text-paper/45"}>{value ? "yes" : "no"}</span>
        </div>
      ))}
      <div className="pt-2 text-xs leading-5 text-paper/55">
        warnings: {recap.data_quality.warnings.length ? recap.data_quality.warnings.join(", ") : "无"}
      </div>
    </div>
  );
}

function StatusPill({ correct }: { correct: boolean | null }) {
  if (correct === true) {
    return <span className="rounded-full border border-emerald-300/30 bg-emerald-300/12 px-4 py-2 text-sm text-emerald-100">模型命中</span>;
  }
  if (correct === false) {
    return <span className="rounded-full border border-danger/35 bg-danger/12 px-4 py-2 text-sm">模型未命中</span>;
  }
  return <span className="rounded-full border border-white/12 px-4 py-2 text-sm text-paper/60">无赛前预测</span>;
}

function predictionText(value: boolean | null): string {
  if (value === true) return "命中";
  if (value === false) return "未命中";
  return "无预测";
}

function reasonText(reason?: string): string {
  if (reason === "match_not_finished_or_result_missing") return "比赛尚未完赛，或赛果尚未回填。";
  if (reason === "match_not_found") return "未找到这场比赛。";
  return "复盘将在比赛结束并回填赛果后生成。";
}
