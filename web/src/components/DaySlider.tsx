import { useEffect, useMemo, useState } from "react";

import { dayName, dayShort } from "../lib/format";
import { Icon } from "./Icon";

/** How long the player leaves each day on the map once it is drawn. */
const PLAY_STEP_MS = 800;

/**
 * A slider over `days` (newest first in the prop, oldest on the left of the track). The label follows the thumb at
 * once; the day is only asked for once the thumb rests for a moment, so a drag across a month is one request.
 * Play walks forward one day at a time (from the oldest when the thumb is at the newest), moving on only once the
 * shown day has arrived, so a slow answer never skips a day. Touching the slider pauses it.
 */
export function DaySlider({ days, value, onChange, onPlay }: {
  days: string[];
  value: string;
  onChange: (day: string) => void;
  /** Called when play starts, to fetch every day at once instead of one per step. */
  onPlay?: (days: string[]) => void;
}) {
  const ordered = useMemo(() => [...days].reverse(), [days]);
  const last = ordered.length - 1;
  const [position, setPosition] = useState(() => Math.max(0, ordered.indexOf(value)));
  const [playing, setPlaying] = useState(false);
  useEffect(() => setPosition(Math.max(0, ordered.indexOf(value))), [ordered, value]);
  useEffect(() => {
    const day = ordered[position];
    if (day === undefined || day === value) return;
    const timer = window.setTimeout(() => onChange(day), playing ? 0 : 250);
    return () => window.clearTimeout(timer);
  }, [ordered, position, value, onChange, playing]);
  useEffect(() => {
    if (!playing || ordered[position] !== value) return; // waits for the day on the thumb to be drawn
    const timer = window.setTimeout(() => {
      if (position >= last) setPlaying(false);
      else setPosition(position + 1);
    }, PLAY_STEP_MS);
    return () => window.clearTimeout(timer);
  }, [playing, position, value, ordered, last]);

  const toggle = () => {
    if (!playing) onPlay?.(ordered);
    if (!playing && position >= last) setPosition(0);
    setPlaying(!playing);
  };
  const day = ordered[position] ?? value;
  return (
    <div className="day-slider">
      <button type="button" className="play" onClick={toggle} aria-label={playing ? "Pausar" : "Reproducir día a día"}>
        <Icon name={playing ? "pause" : "play"} size={16} />
      </button>
      <input
        type="range"
        min={0}
        max={last}
        step={1}
        value={position}
        aria-label="Día"
        aria-valuetext={dayName(day)}
        onChange={(e) => {
          setPlaying(false);
          setPosition(Number(e.target.value));
        }}
      />
      <output>{dayShort(day)}</output>
    </div>
  );
}
