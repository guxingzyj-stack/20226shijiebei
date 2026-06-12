import type { HealthStatus } from "../api/types";

export function BettingOpenStatusCard({ health }: { health?: HealthStatus | null }) {
  if (!health) {
    return <div className="text-sm text-paper/60">投注开放状态加载中。</div>;
  }
  const status = health.betting_open_gate_status || "WAIT";
  const blockers = health.betting_open_blockers || [];
  const warnings = health.betting_open_warnings || [];
  return (
    <div className="space-y-3 text-sm">
      <div className="flex items-center justify-between rounded-lg bg-white/5 px-3 py-2">
        <span className="text-paper/60">闸门状态</span>
        <span className={status === "PASS" ? "text-emerald-200" : "text-gold"}>{status}</span>
      </div>
      <div className="flex items-center justify-between rounded-lg bg-white/5 px-3 py-2">
        <span className="text-paper/60">是否建议开放投注</span>
        <span className="font-semibold text-danger">{health.recommend_open_betting ? "需要人工确认" : "否"}</span>
      </div>
      {blockers.length ? (
        <div className="rounded-lg border border-gold/25 bg-gold/10 p-3 text-xs text-paper/70">
          <div className="mb-1 font-medium text-gold">仍需处理</div>
          {blockers.slice(0, 3).map((item) => <div key={item}>- {item}</div>)}
        </div>
      ) : null}
      {warnings.length ? <div className="text-xs text-paper/45">提示：{warnings.slice(0, 2).join("；")}</div> : null}
      <div className="text-xs text-paper/45">当前页面只展示模拟研究信息，不提供真实购彩服务。</div>
    </div>
  );
}
