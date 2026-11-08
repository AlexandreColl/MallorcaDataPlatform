// Line icons (24x24, stroke = currentColor) for the menu, the theme button and the day player.

const PATHS = {
  home: "M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6h-6v6H4a1 1 0 0 1-1-1z",
  tourism: "M2 16.5h20M5 16.5 3 9l3 .5 2.5 4 5-1-3-8 2.5.5 5.5 7.5 3.5-.5a1.5 1.5 0 0 1 .3 3L5 16.5z",
  water: "M12 3s6 6.5 6 11a6 6 0 0 1-12 0c0-4.5 6-11 6-11z",
  mobility:
    "M6 17V6a3 3 0 0 1 3-3h6a3 3 0 0 1 3 3v11M6 17h12M6 17v2m12-2v2M6 11h12M8.5 14h.01M15.5 14h.01",
  weather:
    "M8 15a4 4 0 1 1 3.8-5.2A3.5 3.5 0 1 1 15.5 17H8a3 3 0 0 1 0-6M17 3v1.5M21 7h-1.5M19.8 4.2l-1 1",
  operations: "M3 12h4l2.5-6 5 12 2.5-6h4",
  explore: "M4 4v16h16M7.5 15l3.5-4.5 3 2.5 5-6.5",
  sun: "M12 4V2m0 20v-2m8-8h2M2 12h2m13.7-5.7 1.4-1.4M4.9 19.1l1.4-1.4m0-11.4L4.9 4.9m14.2 14.2-1.4-1.4M12 16a4 4 0 1 0 0-8 4 4 0 0 0 0 8z",
  moon: "M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z",
  menu: "M4 6h16M4 12h16M4 18h16",
  close: "M6 6l12 12M18 6 6 18",
  play: "M7 4.5v15a.5.5 0 0 0 .8.4l11-7.5a.5.5 0 0 0 0-.8l-11-7.5a.5.5 0 0 0-.8.4z",
  pause: "M8 5v14M16 5v14",
} as const;

export type IconName = keyof typeof PATHS;

export function Icon({ name, size = 20 }: { name: IconName; size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={PATHS[name]} />
    </svg>
  );
}
