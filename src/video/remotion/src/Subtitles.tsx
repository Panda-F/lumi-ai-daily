import React from "react";
import { useCurrentFrame } from "remotion";
import { fonts, subtitlePanel } from "./theme";
import type { SubtitleCue } from "./types";

export const Subtitles: React.FC<{
  cues: SubtitleCue[];
  layoutWidth: number;
  layoutHeight: number;
}> = ({ cues, layoutWidth, layoutHeight }) => {
  const frame = useCurrentFrame();
  const activeCue = cues.find((cue) => frame >= cue.start_frame && frame < cue.end_frame) ?? null;

  if (!activeCue || !activeCue.text.trim()) {
    return null;
  }

  const cueDuration = Math.max(1, activeCue.end_frame - activeCue.start_frame);
  const fadeSpan = Math.max(1, Math.min(6, Math.floor(cueDuration / 2)));
  const fadeIn = Math.max(0, Math.min(1, (frame - activeCue.start_frame) / fadeSpan));
  const fadeOut = Math.max(0, Math.min(1, (activeCue.end_frame - frame) / fadeSpan));
  const opacity = Math.min(fadeIn, fadeOut);
  const translateY = 12 * (1 - fadeIn);
  const charCount = [...activeCue.text].length;
  const fontSize = charCount > 32 ? 32 : charCount > 26 ? 36 : charCount > 20 ? 42 : 48;
  const horizontalPadding = charCount > 28 ? 22 : 28;

  return (
    <div
      style={{
        position: "absolute",
        left: 0,
        right: 0,
        bottom: 116,
        display: "flex",
        justifyContent: "center",
        pointerEvents: "none",
        opacity,
        transform: `translateY(${translateY}px)`
      }}
    >
      <div
        style={{
          maxWidth: Math.min(layoutWidth - 160, 1320),
          minWidth: 320,
          padding: `10px ${horizontalPadding}px`,
          borderRadius: subtitlePanel.radius,
          background: subtitlePanel.background,
          border: subtitlePanel.border,
          boxShadow: subtitlePanel.shadow,
          color: subtitlePanel.text,
          textAlign: "center",
          fontFamily: fonts.body,
          fontSize,
          lineHeight: 1.14,
          fontWeight: 400,
          letterSpacing: 0,
          whiteSpace: "normal",
          wordBreak: "keep-all",
          overflowWrap: "anywhere",
          backdropFilter: "blur(10px)"
        }}
      >
        {activeCue.text}
      </div>
    </div>
  );
};
