import type { Match, OddsMap, Prediction } from "../api/types";

export type Outcome = "home" | "draw" | "away";

export type OutcomeProbabilities = {
  home: number;
  draw: number;
  away: number;
};

export type ScoreMatrixTopScore = {
  home: number;
  away: number;
  probability: number;
};

export type ScoreMatrixSummary = {
  expectedHome: number;
  expectedAway: number;
  expectedTotal: number;
  topScores: ScoreMatrixTopScore[];
};

export function asProbability(value: string | number | null | undefined): number {
  const number = Number(value);
  if (!Number.isFinite(number)) return 0;
  return number > 1 ? number / 100 : number;
}

export function hasCompleteResult(match: Match): boolean {
  return (
    ["finished", "completed"].includes(match.status) &&
    match.result_home !== null &&
    match.result_home !== undefined &&
    match.result_away !== null &&
    match.result_away !== undefined
  );
}

export function resultOutcome(match: Match): Outcome | null {
  if (!hasCompleteResult(match)) return null;
  const home = Number(match.result_home);
  const away = Number(match.result_away);
  if (home > away) return "home";
  if (home < away) return "away";
  return "draw";
}

export function predictionProbabilities(prediction?: Prediction | null): OutcomeProbabilities | null {
  if (!prediction) return null;
  return {
    home: asProbability(prediction.p_home),
    draw: asProbability(prediction.p_draw),
    away: asProbability(prediction.p_away),
  };
}

export function marketProbabilities(odds?: OddsMap | null): OutcomeProbabilities | null {
  if (!odds) return null;
  const homeOdds = Number(odds["3"]);
  const drawOdds = Number(odds["1"]);
  const awayOdds = Number(odds["0"]);
  if (![homeOdds, drawOdds, awayOdds].every((value) => Number.isFinite(value) && value > 0)) {
    return null;
  }
  const raw = {
    home: 1 / homeOdds,
    draw: 1 / drawOdds,
    away: 1 / awayOdds,
  };
  const total = raw.home + raw.draw + raw.away;
  return {
    home: raw.home / total,
    draw: raw.draw / total,
    away: raw.away / total,
  };
}

export function dominantOutcome(probs?: OutcomeProbabilities | null): Outcome | null {
  if (!probs) return null;
  const entries: Array<[Outcome, number]> = [
    ["home", probs.home],
    ["draw", probs.draw],
    ["away", probs.away],
  ];
  return entries.sort((left, right) => right[1] - left[1])[0][0];
}

export function predictionHit(match: Match, prediction?: Prediction | null): boolean | null {
  const actual = resultOutcome(match);
  const predicted = dominantOutcome(predictionProbabilities(prediction));
  if (!actual || !predicted) return null;
  return actual === predicted;
}

export function outcomeLabel(outcome?: Outcome | null): string {
  if (outcome === "home") return "主胜";
  if (outcome === "draw") return "平局";
  if (outcome === "away") return "客胜";
  return "无预测";
}

export function normalizeScoreMatrix(matrix?: number[][] | null): number[][] | null {
  if (!matrix?.length) return null;
  const flat = matrix.flat().map((value) => Number(value || 0));
  const total = flat.reduce((sum, value) => sum + value, 0);
  const divisor = total > 1.5 ? 100 : 1;
  return matrix.map((row) => row.map((value) => Number(value || 0) / divisor));
}

export function summarizeScoreMatrix(matrix?: number[][] | null): ScoreMatrixSummary | null {
  const normalized = normalizeScoreMatrix(matrix);
  if (!normalized?.length) return null;
  const cells: ScoreMatrixTopScore[] = [];
  let expectedHome = 0;
  let expectedAway = 0;
  normalized.forEach((row, home) => {
    row.forEach((probability, away) => {
      expectedHome += home * probability;
      expectedAway += away * probability;
      cells.push({ home, away, probability });
    });
  });
  return {
    expectedHome,
    expectedAway,
    expectedTotal: expectedHome + expectedAway,
    topScores: cells.sort((left, right) => right.probability - left.probability).slice(0, 3),
  };
}

export function scoreInMatrix(matrix: number[][] | null | undefined, home?: number | null, away?: number | null): boolean {
  if (home === null || home === undefined || away === null || away === undefined || !matrix?.length) return false;
  return home >= 0 && away >= 0 && home < matrix.length && away < (matrix[home]?.length || 0);
}
