import type { TeamFormItem, TeamFormResponse } from "../api/types";

export function TeamFormMini({ data }: { data?: TeamFormResponse | null }) {
  if (!data || data.data_status !== "ok") {
    return <div className="text-sm text-paper/60">历史战绩数据不足，暂不展示近 5 场。</div>;
  }
  return (
    <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-1">
      <TeamFormColumn team={data.home_team} rows={data.home_form} />
      <TeamFormColumn team={data.away_team} rows={data.away_form} />
    </div>
  );
}

function TeamFormColumn({ team, rows }: { team: string; rows: TeamFormItem[] }) {
  return (
    <div className="rounded-lg bg-white/5 p-3">
      <div className="mb-2 text-sm font-semibold">{team}</div>
      {rows.length ? (
        <div className="space-y-2">
          {rows.map((row) => (
            <div key={`${row.date}-${row.opponent}-${row.score}`} className="flex items-center justify-between gap-2 text-xs">
              <span className="truncate text-paper/60">{row.date} vs {row.opponent}</span>
              <span className="shrink-0 text-paper/75">{row.score}</span>
              <OutcomeBadge value={row.outcome} />
            </div>
          ))}
        </div>
      ) : (
        <div className="text-xs text-paper/45">暂无可用历史样本</div>
      )}
    </div>
  );
}

function OutcomeBadge({ value }: { value: string }) {
  const label = value === "W" ? "胜" : value === "D" ? "平" : value === "L" ? "负" : value;
  const className =
    value === "W"
      ? "border-emerald-300/40 text-emerald-200"
      : value === "D"
        ? "border-paper/30 text-paper/70"
        : "border-danger/40 text-danger";
  return <span className={`rounded-full border px-2 py-0.5 ${className}`}>{label}</span>;
}
