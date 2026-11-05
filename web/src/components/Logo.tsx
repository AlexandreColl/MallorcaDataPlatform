// The silhouette of Mallorca (a simplified coastline projected into a 32x32 box), also used by public/favicon.svg.
const ISLAND =
  "M4.0 17.4L4.4 16.5L6.3 14.6L9.1 12.4L11.4 10.8L13.7 9.2L16.4 8.1L18.9 7.5L20.2 7.0L21.7 6.6L20.6 7.7L19.6 8.3" +
  "L20.4 8.9L22.1 8.3L21.5 9.7L20.4 10.3L20.6 11.9L22.5 12.4L24.8 12.2L26.7 12.4L28.0 13.3L27.6 14.6L26.1 17.1" +
  "L24.2 20.1L22.5 22.0L20.4 23.9L18.9 25.4L17.3 23.9L15.4 22.8L13.3 21.2L12.4 19.0L11.2 17.4L9.5 17.9L8.4 19.6" +
  "L7.4 18.5L5.9 18.2L4.8 17.9Z";

export function Logo({ size = 32 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true" className="logo">
      <rect width="32" height="32" rx="8" fill="var(--brand)" />
      <path d={ISLAND} fill="#fff" stroke="#fff" strokeWidth="0.8" strokeLinejoin="round" />
    </svg>
  );
}
