import { useEffect, useState } from "react";
import { Activity, BarChart3, LineChart, PieChart } from "lucide-react";
import { apiGet } from "../api/client";
import type { RecapStatus } from "../api/types";

const insufficientMessage = "完赛场次不足，复盘将在小组赛进行后生成。";

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

  const message = status?.message || insufficientMessage;
  const finished = status?.finished_matches ?? 0;
  const insufficient = status?.status === "insufficient_finished_matches" || !status;

  return (
    <div className="space-y-5">
      <section className="rounded-lg border border-white/10 bg-white/[0.06] p-5 shadow-soft">
        <p className="text-sm font-medium text-gold">复盘</p>
        <h1 className="mt-1 text-2xl font-semibold md:text-3xl">赛后只读分析</h1>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-paper/68">
          当前只展示复盘数据状态。完赛样本不足时不会生成资金曲线、校准曲线或分玩法 ROI。
        </p>
      </section>

      {error ? <div className="rounded-lg border border-danger/40 bg-danger/10 p-4 text-sm">{error}</div> : null}

      <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <RecapCard icon={Activity} title="当前复盘状态" value={status?.status || "loading"} detail={message} />
        <RecapCard icon={BarChart3} title="已完赛场次数" value={finished} detail="达到样本阈值后生成复盘" />
        <RecapCard icon={LineChart} title="校准曲线" value={calibration?.status || "loading"} detail={insufficient ? insufficientMessage : "待生成"} />
        <RecapCard icon={PieChart} title="分玩法 ROI" value={plays?.status || "loading"} detail={insufficient ? insufficientMessage : "待生成"} />
      </section>

      <section className="grid gap-4 lg:grid-cols-2">
        <PlaceholderPanel title="校准曲线占位" status={calibration?.status} />
        <PlaceholderPanel title="资金曲线占位" status={funds?.status} />
        <PlaceholderPanel title="分玩法 ROI 占位" status={plays?.status} />
      </section>
    </div>
  );
}

function RecapCard({
  icon: Icon,
  title,
  value,
  detail,
}: {
  icon: typeof Activity;
  title: string;
  value: string | number;
  detail: string;
}) {
  return (
    <div className="rounded-lg border border-white/10 bg-white/[0.055] p-4">
      <div className="flex items-center gap-2 text-sm text-paper/60">
        <Icon size={17} className="text-gold" />
        {title}
      </div>
      <div className="mt-3 text-xl font-semibold text-paper">{value}</div>
      <div className="mt-2 text-xs leading-5 text-paper/55">{detail}</div>
    </div>
  );
}

function PlaceholderPanel({ title, status }: { title: string; status?: string }) {
  const blocked = !status || status === "insufficient_finished_matches";
  return (
    <div className="rounded-lg border border-white/10 bg-white/[0.05] p-5">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-base font-semibold">{title}</h2>
        <span className="rounded-md bg-pitch/80 px-2 py-1 text-xs text-paper/55">{status || "loading"}</span>
      </div>
      <div className="mt-5 flex h-32 items-center justify-center rounded-lg border border-dashed border-white/15 text-center text-sm text-paper/55">
        {blocked ? insufficientMessage : "复盘数据准备中"}
      </div>
    </div>
  );
}
