/** Validated categorical/sequential/status tokens for the Analytics
 * Dashboard's charts - see the dataviz skill's `references/palette.md`. Slot
 * order is the CVD-safety mechanism (adjacent pairs clear the gate in this
 * order); never cycle or reassign a course's slot once picked. Light-mode
 * only, matching the rest of this app (no dark theme exists yet). */
export const CATEGORICAL: string[] = [
  "#2a78d6", // 1 blue
  "#eb6834", // 2 orange
  "#1baf7a", // 3 aqua
  "#eda100", // 4 yellow
  "#e87ba4", // 5 magenta
  "#008300", // 6 green
  "#4a3aa7", // 7 violet
  "#e34948", // 8 red
];

export const SEQUENTIAL_BLUE = "#2a78d6";

/** The app's matcha brand color (same hex as the `matcha-600` Tailwind
 * token in index.css), used for single-series charts where there's no
 * multi-course identity to distinguish - just one measure, so it reads as
 * "this app" rather than needing a slot from the CVD-validated order above. */
export const ACCENT = "#5a8036";

/** Warm, stone-toned ink so chart text/gridlines sit comfortably on the
 * app's cream/white surfaces instead of the validated palette's cooler
 * neutral defaults. */
export const INK = {
  primary: "#211f1a",
  secondary: "#57534e",
  muted: "#8a8478",
  grid: "#e7e3d9",
  axis: "#cbc5b6",
};

/** Stable color for a course: same course always gets the same slot,
 * independent of chart or fetch order, by sorting on course_id. */
export function colorForCourse(courseId: number, allCourseIds: number[]): string {
  const sorted = [...new Set(allCourseIds)].sort((a, b) => a - b);
  const index = sorted.indexOf(courseId);
  return CATEGORICAL[index % CATEGORICAL.length];
}
