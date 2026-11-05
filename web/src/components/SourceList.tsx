import type { Source } from "../api";
import { age, compact } from "../lib/format";
import { sourceState, STATE_LABELS } from "../lib/sources";

export function SourceList({ sources }: { sources: Source[] }) {
  const sorted = [...sources].sort((a, b) => (a.label ?? a.source).localeCompare(b.label ?? b.source, "es"));
  return (
    <ul className="sources">
      {sorted.map((source) => {
        const state = sourceState(source);
        return (
          <li key={source.source} className="source">
            <span className={`status status-${state}`} title={STATE_LABELS[state]} />
            <div className="source-text">
              <span className="source-name">{source.label ?? source.source}</span>
              <span className="source-meta">
                {compact(source.observations)} valores
                {source.data_age_hours !== null && ` · último dato ${age(source.data_age_hours)}`}
              </span>
            </div>
            <span className={`state state-${state}`}>{STATE_LABELS[state]}</span>
          </li>
        );
      })}
    </ul>
  );
}
