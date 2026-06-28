import { useState } from "react";
import type { QARecord } from "../types";
import { getContext } from "../lib/qa-utils";

export function CollapsibleContext({ record }: { record: QARecord }) {
  const [open, setOpen] = useState(false);
  const text = getContext(record);
  if (!text) return null;

  return (
    <section>
      <button
        className="btn btn-tertiary btn-sm"
        style={{ padding: 0, height: "auto", marginBottom: 8 }}
        onClick={() => setOpen(!open)}
      >
        {open ? "收起" : "展开"}依据段落
      </button>
      {open && <div className="context-block">{text}</div>}
    </section>
  );
}
