/** A reusable field-reference table: field / type / default / notes. Used for the
 * top-level request body and for each nested object (constraints, scoring, budget,
 * payload) so every argument gets an explanation, not just the ones at depth 0. */

export interface ParamRow {
  field: string;
  type: string;
  default: string;
  notes: string;
}

export function ParamTable({ rows, dense = false }: { rows: ParamRow[]; dense?: boolean }) {
  return (
    <div className="overflow-hidden rounded-xl border border-border">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-border bg-surface text-[11px] uppercase tracking-wider text-muted-foreground">
            <th className={`px-4 font-mono ${dense ? "py-2" : "py-3"}`}>Field</th>
            <th className={`px-4 font-mono ${dense ? "py-2" : "py-3"}`}>Type</th>
            <th className={`px-4 font-mono ${dense ? "py-2" : "py-3"}`}>Default</th>
            <th className={`px-4 ${dense ? "py-2" : "py-3"}`}>Notes</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((p) => (
            <tr key={p.field} className="border-b border-border bg-card last:border-b-0">
              <td className={`whitespace-nowrap px-4 font-mono text-xs text-foreground ${dense ? "py-2" : "py-3"}`}>
                {p.field}
              </td>
              <td className={`whitespace-nowrap px-4 font-mono text-xs text-muted-foreground ${dense ? "py-2" : "py-3"}`}>
                {p.type}
              </td>
              <td className={`whitespace-nowrap px-4 font-mono text-xs text-muted-foreground ${dense ? "py-2" : "py-3"}`}>
                {p.default}
              </td>
              <td className={`px-4 text-sm text-muted-foreground ${dense ? "py-2" : "py-3"}`}>{p.notes}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
