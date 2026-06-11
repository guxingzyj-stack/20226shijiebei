import { useEffect, useState } from "react";
import { Activity, BarChart3, LineChart, PieChart } from "lucide-react";
import { apiGet } from "../api/client";
import type { RecapStatus } from "../api/types";

const emptyStateText = "数据积累中，比赛完赛后自动生成。";
const insufficientTitle = "复盘报告还没到生成时间";
const insufficientText = "完赛场次不足，复盘报告暂未生成";

export function getRecapStatusText(status?: string | null): string {
  switch (status) {
    case "ready":
      return "复盘已生成";
    case "pending":
      return "复盘生成中";
    case "insufficient_finished_matches":
      return insufficientText;
    case "no_predictions":
      return "暂无预测数据";
    case "no_finished_matches":
      return "暂无已完赛比赛";
    case "error":
      return "复盘数据暂时不可用";
    case "loading":
    case undefined:
    case null:
    case "":
      return "复盘状态加载中";
    default:
      return "复盘状态待确认";
  }
}

export function RecapPage() {
  const [status, setStatus] = useState<RecapStatus | null>(null);
  const [calibration, setCalibration] = useState<RecapStatus | null>(null);
  const [funds, setFunds] = useState<RecapStatus | null>(null);
  const [plays, setPlays] = useState<RecapStatus | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const [statusResult, calibrationResult, fundsResult, playsResult] = await Promise.all([
          apiGet<RecapStatus>("/recap/status"),
          apiGet<RecapStatus>("/recap/calibration"),
          apiGet<RecapStatus>("/recap/funds"),
          apiGet<RecapStatus>("/recap/plays"),
        ]);
        if (!cancelled) {
          setStatus(statusResult);
          setCalibration(calibrationResult);
          setFunds(fundsResult);
          setPlays(playsResult);
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "复盘数据加载失败");
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, []);

  const finished = status?.finished_matches ?? 0;
  const primaryStatus = status?.status || "loading";
  const isInsufficient = primaryStatus === "insufficient_finished_matches" || !status;

  return (
    <div className="space-y-5">
      <section className="rounded-lg border border-white/10 bg-white/[0.06] p-5 shadow-soft">
        <p className="text-sm font-medium text-gold">复盘</p>
        <h1 className="mt-1 text-2xl font-semibold md:text-3xl">赛后只读分析</h1>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-paper/68">
          复盘会在真实比赛完赛后生成，用于检查预测表现、风险暴露和虚拟资金变化。
        </p>
      </section>

      {error ? <div className="rounded-lg border border-danger/40 bg-danger/10 p-4 text-sm">{error}</div> : null}

      {isInsufficient ? (
        <section className="rounded-lg border border-gold/25 bg-gold/10 p-5">
          <h2 className="text-lg font-semibold text-gold">{insufficientTitle}</h2>
          <p className="mt-3 text-sm leading-6 text-paper/72">
            目前系统已经开始记录预测、赔率和虚拟资金数据。等真实比赛陆续完赛后，这里会展示：
          </p>
          <ul className="mt-3 grid gap-2 text-sm text-paper/70 md:grid-cols-2">
            <li>预测校准情况</li>
            <li>不同玩法表现</li>
            <li>虚拟资金曲线</li>
            <li>命中率与风险提示</li>
          </ul>
        </section>
      ) : null}

      <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <RecapCard icon={Activity} title="当前状态" value={getRecapStatusText(primaryStatus)} detail={`已完赛 ${finished} 场`} rawStatus={primaryStatus} />
        <RecapCard icon={BarChart3} title="预测校准" value={getRecapStatusText(calibration?.status)} detail={emptyStateText} rawStatus={calibration?.status} />
        <RecapCard icon={LineChart} title="资金曲线" value={getRecapStatusText(funds?.status)} detail={emptyStateText} rawStatus={funds?.status} />
        <RecapCard icon={PieChart} title="玩法表现" value={getRecapStatusText(plays?.status)} detail={emptyStateText} rawStatus={plays?.status} />
      </section>

      <section className="grid gap-4 lg:grid-cols-2">
        <PlaceholderPanel title="预测校准" status={calibration?.status} />
        <PlaceholderPanel title="资金曲线" status={funds?.status} />
        <PlaceholderPanel title="玩法表现" status={plays?.status} />
      </section>

      <section className="rounded-lg border border-white/10 bg-white/[0.045] p-4 text-sm leading-6 text-paper/62">
        本系统仅用于世界杯预测研究与虚拟资金模拟，不提供真实购彩服务。竞彩长期期望为负，请理性娱乐。
      </section>
    </div>
  );
}

function RecapCard({
  icon: Icon,
  title,
  value,
  detail,
  rawStatus,
}: {
  icon: typeof Activity;
  title: string;
  value: string;
  detail: string;
  rawStatus?: string | null;
}) {
  const shouldShowRawStatus = rawStatus && !["ready", "pending", "loading"].includes(rawStatus);
  return (
    <div className="rounded-lg border border-white/10 bg-white/[0.055] p-4">
      <div className="flex items-center gap-2 text-sm text-paper/60">
        <Icon size={17} className="text-gold" />
        {title}
      </div>
      <div className="mt-3 text-lg font-semibold leading-7 text-paper">{value}</div>
      <div className="mt-2 text-xs leading-5 text-paper/55">{detail}</div>
      {shouldShowRawStatus ? <div className="mt-2 text-[11px] text-paper/40">状态码：{rawStatus}</div> : null}
    </div>
  );
}

function PlaceholderPanel({ title, status }: { title: string; status?: string | null }) {
  return (
    <div className="rounded-lg border border-white/10 bg-white/[0.05] p-5">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-base font-semibold">{title}</h2>
        <span className="rounded-md bg-pitch/80 px-2 py-1 text-xs text-paper/55">{getRecapStatusText(status)}</span>
      </div>
      <div className="mt-5 flex min-h-32 items-center justify-center rounded-lg border border-dashed border-white/15 px-4 text-center text-sm leading-6 text-paper/58">
        {emptyStateText}
      </div>
      {status ? <div className="mt-3 text-right text-[11px] text-paper/38">状态码：{status}</div> : null}
    </div>
  );
}
