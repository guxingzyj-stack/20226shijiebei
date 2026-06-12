export type GlossaryItem = {
  term: string;
  short: string;
  detail?: string;
  category: "模型" | "赔率" | "EV" | "结算" | "健康" | "安全";
};

export const glossary = {
  modelPrediction: {
    term: "模型预测",
    short: "系统根据赔率、球队数据和历史逻辑生成的胜平负概率判断。",
    category: "模型",
  },
  modelHit: {
    term: "模型命中",
    short: "模型赛前最看好的方向，与最终赛果一致。",
    category: "模型",
  },
  hitRate: {
    term: "命中率",
    short: "模型命中的比赛数 / 有效复盘比赛数。样本少时只适合观察。",
    category: "模型",
  },
  modelVersion: {
    term: "model_version",
    short: "模型版本号，用来追踪某次预测由哪个模型生成。",
    category: "模型",
  },
  had: {
    term: "HAD",
    short: "胜平负玩法，3=主胜，1=平局，0=客胜。",
    category: "赔率",
  },
  odds: {
    term: "赔率",
    short: "市场给出的赔付倍数。赔率越低，市场越看好。",
    category: "赔率",
  },
  impliedProbability: {
    term: "隐含概率",
    short: "由赔率反推出来的市场倾向，不是官方真实概率。",
    category: "赔率",
  },
  marketFavorite: {
    term: "市场热门方向",
    short: "赔率最低的一方，代表市场更看好的一方。",
    category: "赔率",
  },
  openingOdds: {
    term: "开盘赔率",
    short: "系统最早采集到的赔率。",
    category: "赔率",
  },
  closingOdds: {
    term: "收盘赔率",
    short: "开赛前最后采集到的赔率。",
    category: "赔率",
  },
  ev: {
    term: "EV",
    short: "模型认为赔率是否被低估的研究分数。EV 越高，分歧越大；但 EV 不是中奖概率，也不是投注建议。",
    category: "EV",
  },
  evValue: {
    term: "EV 值",
    short: "可以理解为“这个选项值不值得研究”的分数。",
    detail:
      "EV > 0：模型觉得赔率可能被低估，有研究价值。EV = 0：模型和市场判断差不多。EV < 0：模型觉得不划算，通常不用重点看。",
    category: "EV",
  },
  evSignal: {
    term: "EV 信号",
    short: "系统发现的研究信号，不是中奖概率，也不是投注建议。",
    category: "EV",
  },
  highEv: {
    term: "高 EV",
    short: "模型和市场分歧较大的研究信号。特别高的 EV 通常是冷门比分，只适合复盘研究。",
    category: "EV",
  },
  researchSignal: {
    term: "研究信号",
    short: "只用于观察模型和市场的分歧，不代表应该下注。",
    category: "EV",
  },
  researchOnly: {
    term: "research_only",
    short: "仅用于研究和复盘，不开放为投注建议。",
    category: "EV",
  },
  suggestionEligible: {
    term: "suggestion_eligible",
    short: "满足更严格条件的候选信号；当前系统仍不提供真实购彩建议。",
    category: "EV",
  },
  evMiss: {
    term: "复盘未命中",
    short: "该研究信号方向与实际赛果不一致。",
    category: "EV",
  },
  settledBets: {
    term: "settled_bets",
    short: "已结算注单数量。",
    category: "结算",
  },
  wonBets: {
    term: "won_bets",
    short: "中奖注单数量。",
    category: "结算",
  },
  lostBets: {
    term: "lost_bets",
    short: "未中奖注单数量。",
    category: "结算",
  },
  voidBets: {
    term: "void_bets",
    short: "无效或退款注单数量。",
    category: "结算",
  },
  openBets: {
    term: "open_bets",
    short: "尚未结算注单数量。",
    category: "结算",
  },
  noPublicBets: {
    term: "no_public_bets",
    short: "当前没有公开用户注单参与该场比赛。",
    category: "结算",
  },
  schedulerStale: {
    term: "scheduler_stale",
    short: "后台调度器是否长时间没有运行。false 表示正常。",
    category: "健康",
  },
  opsHealthStatus: {
    term: "ops_health_status",
    short: "系统自动巡检结果。OK=正常，WARN=提示，FAIL=需要处理。",
    category: "健康",
  },
  noOpenBetsToSettle: {
    term: "no_open_bets_to_settle",
    short: "当前没有待结算注单，不是故障。",
    category: "健康",
  },
  insufficientFinishedMatches: {
    term: "insufficient_finished_matches",
    short: "完赛样本不足，暂时不能做长期模型校准。",
    category: "健康",
  },
  p3Wait: {
    term: "P3 WAIT",
    short: "球员/球队增强数据还在积累，不影响当前预测和复盘。",
    category: "健康",
  },
  roi: {
    term: "ROI",
    short: "虚拟资金收益率，只反映模拟游戏表现，不代表真实收益。",
    category: "安全",
  },
  sampleSmall: {
    term: "样本不足",
    short: "当前完赛比赛还少，统计结果只适合观察，不适合下结论。",
    category: "安全",
  },
} satisfies Record<string, GlossaryItem>;

export type GlossaryKey = keyof typeof glossary;

export const glossaryItems = Object.values(glossary);

export const evValueGuide = {
  title: "EV 值怎么看？",
  intro: "EV 值可以理解为“这个选项值不值得研究”的分数。",
  short:
    "EV 是模型和市场赔率之间的差异分数。EV 大于 0 代表有研究价值，但不代表一定会中，也不是投注建议。",
  bands: [
    "0 以下：不看",
    "0～0.05：意义不大",
    "0.05～0.20：可以关注",
    "0.20 以上：模型和市场分歧很大，要谨慎",
    "特别高的 EV：通常是冷门比分，只适合复盘研究",
  ],
  oneLine: "EV 越大，说明模型越觉得“赔率可能被低估”；但 EV 不是中奖概率，也不是投注建议。",
  scoreRisk: "提示：比分类 EV 往往数值很高，但波动也最大，建议只作为复盘研究。",
};
