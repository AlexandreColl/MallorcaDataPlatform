import { number } from "../lib/format";
import { type Correlation, strength } from "../lib/stats";

function signedR(r: number): string {
  return `${r < 0 ? "−" : r > 0 ? "+" : ""}${number(Math.abs(r), 2)}`;
}

/**
 * How two monthly series move together: Pearson's r of the raw months (season included) and of the months without
 * their yearly cycle, which is the one that says whether one series really follows the other.
 */
export function CorrelationCard({ label, raw, deseasonalized, color }: {
  label: string;
  raw: Correlation | null;
  deseasonalized: Correlation | null;
  color: string;
}) {
  return (
    <article className="card kpi correlation" style={{ "--accent": color } as React.CSSProperties}>
      <header className="kpi-header">
        <h3>{label}</h3>
        <span className="kpi-month">Correlación de Pearson · {raw ? `${number(raw.n)} meses` : "sin datos"}</span>
      </header>
      {raw ? (
        <>
          <p className="kpi-value">
            <span className="kpi-unit r">r</span> {signedR(raw.r)}
          </p>
          <p className="chip chip-neutral">{strength(raw.r)}</p>
          {deseasonalized && (
            <p className="correlation-note">
              Sin el ciclo anual: <strong>r {signedR(deseasonalized.r)}</strong> · {strength(deseasonalized.r).toLowerCase()}
            </p>
          )}
        </>
      ) : (
        <p className="empty">No hay meses suficientes con las dos series.</p>
      )}
    </article>
  );
}
