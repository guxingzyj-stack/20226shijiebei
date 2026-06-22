export function toNumber(value: string | number | null | undefined): number {
  if (value === null || value === undefined) return 0;
  return Number(value);
}

export function formatPercent(value: string | number | null | undefined): string {
  const number = toNumber(value);
  if (!Number.isFinite(number)) return "-";
  return `${(number * 100).toFixed(1)}%`;
}

export function formatDecimal(value: string | number | null | undefined, digits = 2): string {
  const number = toNumber(value);
  if (!Number.isFinite(number)) return "-";
  return number.toFixed(digits);
}

export function formatMoney(value: string | number | null | undefined): string {
  const number = toNumber(value);
  if (!Number.isFinite(number)) return "-";
  return number.toLocaleString("zh-CN", { minimumFractionDigits: 0, maximumFractionDigits: 2 });
}

export function formatDateTime(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

export function formatDateKey(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "long",
    day: "numeric",
    weekday: "short",
  }).format(new Date(value));
}

export function playTypeLabel(playType: string): string {
  const labels: Record<string, string> = {
    had: "胜平负",
    hhad: "让球胜平负",
    crs: "正确比分",
    correct_score: "正确比分",
    ttg: "总进球",
    hafu: "半全场",
  };
  return labels[playType] || playType;
}

export function selectionLabel(selection: string): string {
  const labels: Record<string, string> = {
    "3": "主胜",
    "1": "平局",
    "0": "客胜",
    other_home_win: "其他主胜",
    other_draw: "其他平局",
    other_away_win: "其他客胜",
    胜其他: "其他主胜",
    胜其它: "其他主胜",
    平其他: "其他平局",
    平其它: "其他平局",
    负其他: "其他客胜",
    负其它: "其他客胜",
  };
  return labels[selection] || selection.replace(":", "-");
}
