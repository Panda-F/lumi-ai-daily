export const palette = {
  bg: "#FFF8F5",
  bgSoft: "#FFF0F8",
  bgAlt: "#F5F0FF",
  ink: "#1C1C1E",
  text: "#1C1C1E",
  textSoft: "#374151",
  muted: "#6B7280",
  weakText: "#9CA3AF",
  accent: "#F472B6",
  deep: "#EC4899",
  purple: "#C084FC",
  accentSoft: "rgba(244, 114, 182, 0.12)",
  chromeBorder: "rgba(244, 114, 182, 0.22)",
  cardBorder: "rgba(244, 114, 182, 0.18)",
  panel: "rgba(255,255,255,0.88)",
  white: "#FFFFFF",
  shadow: "rgba(236, 72, 153, 0.10)",
  subtitleBar: "rgba(76, 76, 78, 0.92)",
  subtitleBorder: "rgba(255,255,255,0.06)"
} as const;

export const subtitlePanel = {
  background: palette.subtitleBar,
  border: `1px solid ${palette.subtitleBorder}`,
  shadow: "0 10px 20px rgba(0,0,0,0.12)",
  radius: 2,
  text: "rgba(255,255,255,0.98)"
} as const;

export const fonts = {
  display: '-apple-system, "PingFang SC", "Helvetica Neue", sans-serif',
  title: '-apple-system, "PingFang SC", "Helvetica Neue", sans-serif',
  body: '-apple-system, "PingFang SC", "Helvetica Neue", sans-serif',
  mono: '"SF Mono", "Menlo", monospace'
} as const;
