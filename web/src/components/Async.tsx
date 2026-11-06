import type { ReactNode } from "react";

import type { Loaded } from "../hooks";

/** Shows a skeleton while the data loads, the error if it fails and the content once it is there. */
export function Async<T>({ state, height = 280, children }: {
  state: Loaded<T>;
  height?: number;
  children: (data: T) => ReactNode;
}) {
  if (state.status === "loading") return <div className="block skeleton" style={{ height }} aria-busy="true" />;
  if (state.status === "error") return <p className="error">No se pudieron cargar los datos: {state.error}</p>;
  return <>{children(state.data)}</>;
}

export interface Column<Row> {
  label: string;
  value: (row: Row) => ReactNode;
  numeric?: boolean;
}

/** A compact table; numeric columns are right-aligned with tabular figures. */
export function Table<Row>({ rows, columns, empty = "Sin datos" }: {
  rows: Row[];
  columns: Column<Row>[];
  empty?: string;
}) {
  if (rows.length === 0) return <p className="empty">{empty}</p>;
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c.label} className={c.numeric ? "num" : undefined}>
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i}>
              {columns.map((c) => (
                <td key={c.label} className={c.numeric ? "num" : undefined}>
                  {c.value(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
