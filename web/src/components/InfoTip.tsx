import { HelpCircle } from "lucide-react";
import { useState } from "react";
import { type GlossaryKey, glossary } from "../recaps/glossary";

type InfoTipProps = {
  glossaryKey?: GlossaryKey;
  text?: string;
  label?: string;
};

export function InfoTip({ glossaryKey, text, label }: InfoTipProps) {
  const [open, setOpen] = useState(false);
  const item = glossaryKey ? glossary[glossaryKey] : null;
  const content = text || item?.short || "";
  const title = label || item?.term || "说明";

  if (!content) return null;

  return (
    <span className="group relative inline-flex align-middle">
      <button
        type="button"
        aria-label={`${title}说明`}
        title={content}
        onClick={(event) => {
          event.preventDefault();
          event.stopPropagation();
          setOpen((value) => !value);
        }}
        onBlur={() => window.setTimeout(() => setOpen(false), 120)}
        className="ml-1 inline-flex h-5 w-5 items-center justify-center rounded-full border border-gold/35 bg-gold/10 text-gold transition hover:bg-gold/20"
      >
        <HelpCircle size={13} />
      </button>
      <span
        className={`absolute left-1/2 top-7 z-50 w-64 -translate-x-1/2 rounded-lg border border-gold/25 bg-[#123f2e] p-3 text-left text-xs leading-5 text-paper shadow-soft ${
          open ? "block" : "hidden group-hover:block"
        }`}
      >
        <span className="mb-1 block font-semibold text-gold">{title}</span>
        {content}
      </span>
    </span>
  );
}
