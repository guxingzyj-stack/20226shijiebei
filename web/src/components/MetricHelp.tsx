import { type ReactNode } from "react";
import { type GlossaryKey, glossary } from "../recaps/glossary";

type MetricHelpProps = {
  glossaryKey?: GlossaryKey;
  title?: string;
  children?: ReactNode;
};

export function MetricHelp({ glossaryKey, title, children }: MetricHelpProps) {
  const item = glossaryKey ? glossary[glossaryKey] : null;
  return (
    <div className="rounded-lg border border-white/10 bg-pitch/55 p-3 text-xs leading-5 text-paper/62">
      <div className="mb-1 font-semibold text-gold">{title || item?.term || "这是什么？"}</div>
      {children || item?.short}
    </div>
  );
}
