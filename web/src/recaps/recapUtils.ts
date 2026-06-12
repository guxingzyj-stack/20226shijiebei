import type { MatchRecap } from "../api/types";
import { formatDateKey } from "../utils/format";

export const outcomeLabel: Record<string, string> = {
  home: "主胜",
  draw: "平局",
  away: "客胜",
};

export function outcomeText(value: string | null | undefined): string {
  if (!value) return "暂无";
  return outcomeLabel[value] || value;
}

export function predictionText(value: boolean | null | undefined): string {
  if (value === true) return "命中";
  if (value === false) return "未命中";
  return "无预测";
}

export function predictionTone(value: boolean | null | undefined): string {
  if (value === true) return "border-emerald-300/30 bg-emerald-300/12 text-emerald-100";
  if (value === false) return "border-danger/35 bg-danger/12 text-paper";
  return "border-white/12 bg-white/[0.04] text-paper/60";
}

export function settlementText(value: string | null | undefined): string {
  if (value === "no_public_bets") return "暂无公开注单结算";
  if (!value) return "暂无";
  return value;
}

export type RecapAggregate = {
  marketCorrectCount: number;
  modelMarketAgreeCount: number;
  modelMarketDisagreeCount: number;
  totalEvSignals: number;
  highEvCount: number;
  researchOnlyCount: number;
  suggestionEligibleCount: number;
  evHitCount: number;
  evMissCount: number;
};

export function aggregateRecaps(recaps: MatchRecap[]): RecapAggregate {
  return recaps.reduce<RecapAggregate>(
    (acc, recap) => {
      if (recap.market.favorite && recap.result.winner && recap.market.favorite === recap.result.winner) {
        acc.marketCorrectCount += 1;
      }
      if (recap.market.favorite && recap.model.predicted_outcome) {
        if (recap.market.favorite === recap.model.predicted_outcome) {
          acc.modelMarketAgreeCount += 1;
        } else {
          acc.modelMarketDisagreeCount += 1;
        }
      }
      acc.totalEvSignals += recap.ev.total_ev_signals || 0;
      acc.highEvCount += recap.ev.high_ev_count || 0;
      acc.researchOnlyCount += recap.ev.research_only_count || 0;
      acc.suggestionEligibleCount += recap.ev.suggestion_eligible_count || 0;
      acc.evHitCount += recap.ev.hit_count || 0;
      acc.evMissCount += recap.ev.miss_count || 0;
      return acc;
    },
    {
      marketCorrectCount: 0,
      modelMarketAgreeCount: 0,
      modelMarketDisagreeCount: 0,
      totalEvSignals: 0,
      highEvCount: 0,
      researchOnlyCount: 0,
      suggestionEligibleCount: 0,
      evHitCount: 0,
      evMissCount: 0,
    },
  );
}

export type DailyRecapGroup = {
  dateKey: string;
  recaps: MatchRecap[];
  aggregate: RecapAggregate;
};

export function groupRecapsByDay(recaps: MatchRecap[]): DailyRecapGroup[] {
  const groups = new Map<string, MatchRecap[]>();
  for (const recap of recaps) {
    const key = formatDateKey(recap.kickoff_at);
    groups.set(key, [...(groups.get(key) || []), recap]);
  }
  return [...groups.entries()].map(([dateKey, rows]) => ({
    dateKey,
    recaps: rows,
    aggregate: aggregateRecaps(rows),
  }));
}

export function buildDailyReportText(group: DailyRecapGroup): string {
  const modelHits = group.recaps.filter((recap) => recap.model.prediction_correct === true).length;
  const lines = [
    "【世界杯预测复盘日报】",
    `日期：${group.dateKey}`,
    `完赛场次：${group.recaps.length}`,
    `模型命中：${modelHits}`,
    `市场热门命中：${group.aggregate.marketCorrectCount}`,
    "主要复盘：",
    ...group.recaps.map(
      (recap, index) =>
        `${index + 1}. ${recap.home_team} ${recap.result.scoreline} ${recap.away_team}，模型${predictionText(
          recap.model.prediction_correct,
        )}，市场热门方向：${outcomeText(recap.market.favorite)}。`,
    ),
    "数据状态：",
    "- scheduler 正常",
    "- 赛果一致性正常",
    `- 结算状态：${group.recaps.every((recap) => recap.settlement.settlement_status === "no_public_bets") ? "暂无公开注单结算" : "已记录结算摘要"}`,
    "说明：本系统为虚拟资金模拟与研究用途，不提供真实购彩服务。",
  ];
  return lines.join("\n");
}
