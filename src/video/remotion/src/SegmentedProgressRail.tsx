import React from "react";
import { fonts, palette } from "./theme";
import { fitText } from "./TextFit";

export type RailState = "past" | "current" | "future";

export type RailSegment = {
  key: string;
  label: string;
  state: RailState;
};

export const SegmentedProgressRail: React.FC<{
  segments: RailSegment[];
  style?: React.CSSProperties;
  labelSize?: number;
  trackWidth?: number;
}> = ({ segments, style, labelSize = 13, trackWidth = 1768 }) => {
  const segmentCount = segments.length;
  const effectiveLabelSize =
    segmentCount >= 12 ? Math.max(10, labelSize - 2) : segmentCount >= 10 ? Math.max(11, labelSize - 1) : segmentCount >= 8 ? Math.max(12, labelSize) : labelSize;
  const railGap = segmentCount >= 12 ? 4 : segmentCount >= 10 ? 6 : segmentCount >= 8 ? 8 : 10;
  const segmentGap = segmentCount >= 10 ? 5 : 7;
  const segmentWidth = Math.max(72, (trackWidth - railGap * Math.max(0, segmentCount - 1)) / Math.max(1, segmentCount));

  return (
    <div
      style={{
        display: "flex",
        alignItems: "stretch",
        gap: railGap,
        ...style
      }}
    >
      {segments.map((segment) => {
        const active = segment.state === "current";
        const past = segment.state === "past";
        const future = segment.state === "future";
        const fitted = fitText(segment.label, {
          maxWidth: Math.max(56, segmentWidth - 8),
          maxFontSize: active ? effectiveLabelSize + 1 : effectiveLabelSize,
          minFontSize: 8,
          maxLines: 2
        });

        return (
          <div
            key={segment.key}
            style={{
              flex: 1,
              minWidth: 0,
              display: "grid",
              gap: segmentGap,
              alignContent: "start"
            }}
          >
            <div
              style={{
                fontFamily: fonts.body,
                fontSize: fitted.fontSize,
                lineHeight: 1.15,
                fontWeight: active ? 800 : 700,
                color: active ? palette.deep : past ? palette.text : palette.weakText,
                opacity: future ? 0.72 : 1,
                textAlign: "center",
                padding: "0 2px",
                whiteSpace: "nowrap",
                overflowWrap: "normal",
                wordBreak: "keep-all",
                minHeight: effectiveLabelSize * 2.25,
                maxHeight: effectiveLabelSize * 2.35,
                display: "flex",
                alignItems: "flex-end",
                justifyContent: "center"
              }}
            >
              <div>
                {fitted.lines.slice(0, 2).map((line, index) => (
                  <div key={`${segment.key}-${line}-${index}`}>{line}</div>
                ))}
              </div>
            </div>
            <div
              style={{
                height: active ? 4 : 3,
                borderRadius: 999,
                background: active
                  ? `linear-gradient(90deg, ${palette.accent} 0%, ${palette.purple} 100%)`
                  : past
                    ? "rgba(31,28,30,0.24)"
                    : "rgba(31,28,30,0.08)",
                boxShadow: active ? "0 0 14px rgba(244,114,182,0.18)" : "none"
              }}
            />
          </div>
        );
      })}
    </div>
  );
};
