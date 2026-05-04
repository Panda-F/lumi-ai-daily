import React from "react";
import { AbsoluteFill } from "remotion";
import { SegmentedProgressRail, type RailSegment } from "./SegmentedProgressRail";
import { bodyFont, monoFont } from "./LumiApprovedVisuals";
import { palette } from "./theme";

export const Header: React.FC<{
  dateLabel: string;
  issueLabel: string;
  activeCategory: string;
  activeIndex: number;
  totalItems: number;
  sceneKind: "cover" | "opening" | "item" | "outro";
  itemLabels?: string[];
}> = ({ dateLabel, issueLabel, activeCategory, activeIndex, totalItems, sceneKind, itemLabels = [] }) => {
  const railLabelSize = totalItems >= 8 ? 12 : 13;
  const segments: RailSegment[] = [
    {
      key: "cover",
      label: "封面",
      state:
        sceneKind === "cover"
          ? "current"
          : sceneKind === "opening" || sceneKind === "item" || sceneKind === "outro"
            ? "past"
            : "future"
    },
    {
      key: "opening",
      label: "开场",
      state:
        sceneKind === "opening"
          ? "current"
          : sceneKind === "item" || sceneKind === "outro"
            ? "past"
            : "future"
    },
    ...Array.from({ length: totalItems }).map((_, index) => {
      const itemIndex = index + 1;
      const state: RailSegment["state"] =
        sceneKind === "outro"
          ? "past"
          : sceneKind === "item"
            ? itemIndex < activeIndex
              ? "past"
              : itemIndex === activeIndex
                ? "current"
                : "future"
            : "future";

      return {
        key: `item-${itemIndex}`,
        label: itemLabels[index] ?? String(itemIndex).padStart(2, "0"),
        state
      };
    }),
    {
      key: "outro",
      label: "结尾",
      state: sceneKind === "outro" ? "current" : "future"
    }
  ];

  return (
    <AbsoluteFill
      style={{
        height: 136,
        boxSizing: "border-box",
        pointerEvents: "none"
      }}
    >
      <div
        style={{
          position: "absolute",
          left: 76,
          right: 76,
          top: 28,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between"
        }}
      >
        <div
          style={{
            padding: "8px 16px",
            borderRadius: 8,
            background: "linear-gradient(135deg, rgba(244,114,182,0.98) 0%, rgba(192,132,252,0.98) 100%)",
            color: "#FFFFFF",
            fontFamily: bodyFont,
            fontSize: 16,
            fontWeight: 700
          }}
        >
          Lumi
        </div>

        <div
          style={{
            fontFamily: monoFont,
            fontSize: 15,
            color: palette.textSoft,
            fontWeight: 600
          }}
        >
          {dateLabel} · {issueLabel}
        </div>
      </div>

      <SegmentedProgressRail
        segments={segments}
        style={{
          position: "absolute",
          left: 76,
          right: 76,
          top: 76
        }}
        labelSize={railLabelSize}
        trackWidth={1768}
      />
      {activeCategory ? (
        <div
          style={{
            position: "absolute",
            left: 76,
            top: 112,
            opacity: 0
          }}
        >
          {activeCategory}
        </div>
      ) : null}
      <div
        style={{
          position: "absolute",
          left: 0,
          right: 0,
          top: 0,
          height: 136,
          pointerEvents: "none",
          background: "linear-gradient(180deg, rgba(255,248,245,0.72) 0%, rgba(255,248,245,0) 100%)"
        }}
      />
      <div
        style={{
          position: "absolute",
          left: 76,
          right: 76,
          top: 124,
          height: 1,
          background: "rgba(244,114,182,0.10)"
        }}
      />
    </AbsoluteFill>
  );
};
