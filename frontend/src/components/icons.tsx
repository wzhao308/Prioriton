/** A small, consistent line-icon set (18px, 1.7 stroke) for the sidebar nav
 * and section headers - kept as one file so every icon shares the same
 * weight/size instead of pulling in a full icon library for six glyphs. */
type IconProps = { className?: string };
const base = { width: 18, height: 18, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.7, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };

export function HomeIcon({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M4 11.5 12 4l8 7.5" />
      <path d="M6 10v9a1 1 0 0 0 1 1h3v-6h4v6h3a1 1 0 0 0 1-1v-9" />
    </svg>
  );
}

export function TimerIcon({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <circle cx="12" cy="13" r="8" />
      <path d="M12 9v4l3 2" />
      <path d="M9.5 2.5h5" />
    </svg>
  );
}

export function ChartIcon({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M4 20V10M11 20V4M18 20v-7" />
      <path d="M3 20h18" />
    </svg>
  );
}

export function SparkleIcon({ className }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" width={18} height={18} className={className}>
      <path
        d="M12 2.5c.6 3.4 1.4 5.6 2.6 6.9 1.3 1.2 3.5 2 6.9 2.6-3.4.6-5.6 1.4-6.9 2.6-1.2 1.3-2 3.5-2.6 6.9-.6-3.4-1.4-5.6-2.6-6.9-1.3-1.2-3.5-2-6.9-2.6 3.4-.6 5.6-1.4 6.9-2.6 1.2-1.3 2-3.5 2.6-6.9Z"
        fill="currentColor"
      />
    </svg>
  );
}

export function CalendarIcon({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <rect x="3.5" y="5" width="17" height="15" rx="2" />
      <path d="M3.5 9.5h17M8 3v4M16 3v4" />
    </svg>
  );
}

export function StackIcon({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="m12 3 8 4.5-8 4.5-8-4.5Z" />
      <path d="m4 12 8 4.5 8-4.5M4 16.5 12 21l8-4.5" />
    </svg>
  );
}

export function GearIcon({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 13a7.7 7.7 0 0 0 0-2l1.9-1.5-2-3.4-2.3.6a7.6 7.6 0 0 0-1.7-1L15 3.4h-4l-.3 2.3a7.6 7.6 0 0 0-1.7 1l-2.3-.6-2 3.4L6.6 11a7.7 7.7 0 0 0 0 2l-1.9 1.5 2 3.4 2.3-.6a7.6 7.6 0 0 0 1.7 1l.3 2.3h4l.3-2.3a7.6 7.6 0 0 0 1.7-1l2.3.6 2-3.4Z" />
    </svg>
  );
}

export function LeafIcon({ className }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" width={16} height={16} className={className}>
      <path d="M7 18c-1-5 2-11 11-11 1 6-2 11-11 11Z" fill="currentColor" />
      <path d="M7 18c2-5 5-7 8-9" stroke="#f4f7ed" strokeWidth="1.3" strokeLinecap="round" fill="none" />
    </svg>
  );
}
