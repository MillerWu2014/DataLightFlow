import type { TaxonomyPreviewNode } from "../types";

function treeBranch(indent: number): string {
  if (indent <= 1) return "└─";
  return `${"│  ".repeat(indent - 1)}└─`;
}

interface TaxonomyPreviewTableProps {
  nodes: TaxonomyPreviewNode[];
}

export function TaxonomyPreviewTable({ nodes }: TaxonomyPreviewTableProps) {
  const rows = nodes.flatMap((node, i) => [
    <div key={`${i}-lvl`} className="taxonomy-cell taxonomy-cell-lvl">
      {node.level}
    </div>,
    <div key={`${i}-node`} className="taxonomy-cell taxonomy-cell-node">
      {node.indent > 0 ? (
        <span className="taxonomy-node-line">
          <span className="taxonomy-branch">{treeBranch(node.indent)}</span>
          <span>{node.label}</span>
        </span>
      ) : (
        node.label
      )}
    </div>,
  ]);

  return (
    <div className="taxonomy-table">
      <div className="taxonomy-grid">
        <div className="taxonomy-cell taxonomy-cell-header taxonomy-cell-lvl">层级</div>
        <div className="taxonomy-cell taxonomy-cell-header">节点描述</div>
        {rows}
      </div>
    </div>
  );
}
