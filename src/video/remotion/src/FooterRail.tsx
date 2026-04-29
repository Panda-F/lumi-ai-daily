import React from "react";
import { AbsoluteFill } from "remotion";
import { stripLeadDecor } from "./helpers";
import { fonts, subtitlePanel } from "./theme";

const stripSubtitleLead = (text: string) =>
  stripLeadDecor(text || "").replace(/^第[\d一二三四五六七八九十]+条[，,。\s]*/u, "").trim();

const SubtitleBubble: React.FC<{ text: string; bottom: number }> = ({ text, bottom }) => {
  if (!text) {
    return null;
  }

  const charCount = [...text].length;
  const fontSize = charCount > 42 ? 30 : charCount > 32 ? 34 : charCount > 24 ? 40 : 46;

  return (
    <div
      style={{
        position: "absolute",
        left: "50%",
        bottom,
        transform: "translateX(-50%)",
        maxWidth: "calc(100% - 180px)",
        display: "flex",
        justifyContent: "center"
      }}
    >
      <div
        style={{
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          minWidth: 360,
          maxWidth: "100%",
          padding: "10px 28px",
          borderRadius: subtitlePanel.radius,
          background: subtitlePanel.background,
          border: subtitlePanel.border,
          boxShadow: subtitlePanel.shadow,
          backdropFilter: "blur(10px)"
        }}
      >
        <div
          style={{
            fontFamily: fonts.body,
            fontSize,
            fontWeight: 400,
            lineHeight: 1.24,
            letterSpacing: 0,
            color: subtitlePanel.text,
            whiteSpace: "normal",
            wordBreak: "break-word",
            overflowWrap: "anywhere",
            overflow: "hidden",
            maxWidth: "100%",
            textAlign: "center",
            display: "block"
          }}
        >
          {text}
        </div>
      </div>
    </div>
  );
};

export const FooterRail: React.FC<{
  items: { title: string }[];
  activeIndex: number;
  currentTitle: string;
  subtitleText: string;
  sceneKind: "cover" | "opening" | "item" | "outro";
  issueLabel: string;
}> = ({ subtitleText }) => {
  const subtitleBubbleText = stripSubtitleLead(subtitleText || "");

  return (
    <AbsoluteFill
      style={{
        pointerEvents: "none",
        justifyContent: "flex-end"
      }}
    >
      <SubtitleBubble text={subtitleBubbleText} bottom={30} />
    </AbsoluteFill>
  );
};
