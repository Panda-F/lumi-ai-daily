import React from "react";
import { Img, staticFile } from "remotion";
import { Icon, type IconName } from "./icons";
import { palette } from "./theme";

export const editorialFont = '"Songti SC", "STSong", "Noto Serif SC", serif';
export const bodyFont = '-apple-system, "PingFang SC", "Helvetica Neue", sans-serif';
export const monoFont = '"SF Mono", "Menlo", monospace';

export const defaultIssueQuote = "计算的目的不是数字，而是洞察。";

export const GlassPanel: React.FC<{ children: React.ReactNode; style?: React.CSSProperties }> = ({ children, style }) => {
  return (
    <div
      style={{
        position: "relative",
        borderRadius: 8,
        background: "linear-gradient(180deg, rgba(255,255,255,0.82) 0%, rgba(255,250,252,0.96) 100%)",
        border: "1px solid rgba(244,114,182,0.14)",
        boxShadow: "0 18px 42px rgba(236,72,153,0.08)",
        overflow: "hidden",
        ...style
      }}
    >
      {children}
    </div>
  );
};

export const AccentBar: React.FC<{ width?: number; style?: React.CSSProperties }> = ({ width = 420, style }) => {
  return (
    <div
      style={{
        width,
        height: 22,
        borderRadius: 999,
        background: "linear-gradient(90deg, rgba(244,114,182,0.18) 0%, rgba(244,114,182,0.04) 100%)",
        ...style
      }}
    />
  );
};

export const BigKeyword: React.FC<{ label: string }> = ({ label }) => {
  return (
    <div
      style={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "14px 20px",
        borderRadius: 8,
        background: "linear-gradient(180deg, rgba(255,255,255,0.84) 0%, rgba(255,248,252,0.96) 100%)",
        border: "1px solid rgba(244,114,182,0.16)",
        color: palette.deep,
        fontFamily: bodyFont,
        fontSize: 28,
        fontWeight: 700,
        lineHeight: 1.1,
        boxShadow: "0 10px 22px rgba(236,72,153,0.05)"
      }}
    >
      {label}
    </div>
  );
};

export const clampLabel = (text: string, maxChars: number) => {
  const chars = [...(text || "").trim()];
  if (chars.length <= maxChars) {
    return chars.join("");
  }
  return `${chars.slice(0, Math.max(1, maxChars)).join("")}`;
};

export const issueQuoteAvatarSrc = (avatarSrc?: string | null) => (avatarSrc ? staticFile(avatarSrc) : null);

export const IssueQuoteBadge: React.FC<{
  text?: string;
  author?: string;
  compact?: boolean;
  hero?: boolean;
  avatarSrc?: string | null;
  style?: React.CSSProperties;
}> = ({ text = defaultIssueQuote, author = "理查德·汉明", compact = false, hero = false, avatarSrc, style }) => {
  const resolvedAvatarSrc = issueQuoteAvatarSrc(avatarSrc);
  const avatarSize = compact ? 42 : hero ? 64 : 46;
  const bodySize = compact ? 15 : hero ? 23 : 19;
  const labelSize = compact ? 13 : hero ? 16 : 14;

  return (
    <GlassPanel
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: compact ? 12 : hero ? 20 : 16,
        padding: compact ? "10px 14px" : hero ? "16px 24px" : "12px 18px",
        maxWidth: compact ? 420 : hero ? 720 : 600,
        background: "rgba(255,255,255,0.64)",
        border: "1px solid rgba(244,114,182,0.12)",
        boxShadow: "0 10px 24px rgba(236,72,153,0.06)",
        backdropFilter: "blur(10px)",
        ...style
      }}
    >
      <div
        style={{
          width: avatarSize,
          height: avatarSize,
          borderRadius: 999,
          overflow: "hidden",
          flexShrink: 0,
          background: "linear-gradient(135deg, #FECDD3 0%, #F5D0FE 100%)"
        }}
      >
        {resolvedAvatarSrc ? (
          <Img src={resolvedAvatarSrc} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
        ) : null}
      </div>
      <div style={{ display: "grid", gap: 3, minWidth: 0 }}>
        <div
          style={{
            fontFamily: bodyFont,
            fontSize: bodySize,
            lineHeight: 1.32,
            color: palette.text,
            fontWeight: 600,
            overflowWrap: "anywhere",
            wordBreak: "break-word"
          }}
        >
          {text}
        </div>
        <div
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 7
          }}
        >
          <div
            style={{
              width: 6,
              height: 6,
              borderRadius: 999,
              background: palette.deep
            }}
          />
          <div
            style={{
              fontFamily: bodyFont,
              fontSize: labelSize,
              lineHeight: 1.2,
              color: palette.deep,
              fontWeight: 700
            }}
          >
            {author}
          </div>
        </div>
      </div>
    </GlassPanel>
  );
};

export const StoryCard: React.FC<{
  title: string;
  icon: IconName;
  children: React.ReactNode;
  minHeight?: number;
}> = ({ title, icon, children, minHeight = 320 }) => {
  return (
    <GlassPanel
      style={{
        background: "linear-gradient(180deg, rgba(255,255,255,0.92) 0%, rgba(255,249,252,0.96) 100%)",
        padding: "24px 24px 26px",
        minHeight
      }}
    >
      <div
        style={{
          display: "grid",
          gap: 18
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 14
          }}
        >
          <div
            style={{
              width: 56,
              height: 56,
              borderRadius: 14,
              background: "rgba(244,114,182,0.12)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center"
            }}
          >
            <Icon name={icon} size={30} color={palette.deep} strokeWidth={1.9} />
          </div>
          <div
            style={{
              fontFamily: bodyFont,
              fontSize: 28,
              lineHeight: 1.2,
              color: palette.text,
              fontWeight: 700
            }}
          >
            {title}
          </div>
        </div>
        <div
          style={{
            display: "grid",
            gap: 14
          }}
        >
          {children}
        </div>
      </div>
    </GlassPanel>
  );
};

export const CardBodyText: React.FC<{ children: React.ReactNode; emphasis?: boolean }> = ({ children, emphasis = false }) => (
  <div
    style={{
      fontFamily: bodyFont,
      fontSize: 24,
      lineHeight: 1.48,
      color: palette.text,
      fontWeight: emphasis ? 600 : 500,
      overflowWrap: "anywhere",
      wordBreak: "break-word"
    }}
  >
    {children}
  </div>
);

export const BulletRow: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div
    style={{
      display: "grid",
      gridTemplateColumns: "12px minmax(0, 1fr)",
      gap: 12,
      alignItems: "start"
    }}
  >
    <div
      style={{
        width: 7,
        height: 7,
        borderRadius: 999,
        background: palette.accent,
        marginTop: 14
      }}
    />
    <div
      style={{
        fontFamily: bodyFont,
        fontSize: 24,
        lineHeight: 1.48,
        color: palette.textSoft,
        fontWeight: 500,
        overflowWrap: "anywhere",
        wordBreak: "break-word"
      }}
    >
      {children}
    </div>
  </div>
);

export const fallbackMediaArtwork = ({
  title,
  icon,
  compact = false
}: {
  title: string;
  icon: IconName;
  compact?: boolean;
}) => (
  <div
    style={{
      position: "relative",
      width: "100%",
      height: "100%",
      overflow: "hidden",
      background: "linear-gradient(135deg, rgba(253,242,248,0.98) 0%, rgba(245,240,255,0.98) 100%)"
    }}
  >
    <div
      style={{
        position: "absolute",
        right: compact ? -22 : -40,
        top: compact ? -18 : -34,
        width: compact ? 180 : 280,
        height: compact ? 180 : 280,
        borderRadius: 999,
        background: "rgba(244,114,182,0.12)"
      }}
    />
    <div
      style={{
        position: "absolute",
        left: compact ? -22 : -38,
        bottom: compact ? -26 : -48,
        width: compact ? 150 : 240,
        height: compact ? 150 : 240,
        borderRadius: 999,
        background: "rgba(192,132,252,0.12)"
      }}
    />
    <div
      style={{
        position: "absolute",
        left: "50%",
        top: "50%",
        transform: "translate(-50%, -58%)",
        width: compact ? 126 : 176,
        height: compact ? 126 : 176,
        borderRadius: 999,
        background: "rgba(255,255,255,0.92)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        boxShadow: "0 18px 40px rgba(244,114,182,0.16)"
      }}
    >
      <Icon name={icon} size={compact ? 56 : 82} color={palette.deep} strokeWidth={1.7} />
    </div>
    <div
      style={{
        position: "absolute",
        left: compact ? 22 : 34,
        right: compact ? 22 : 34,
        bottom: compact ? 20 : 28,
        padding: compact ? "10px 14px" : "16px 18px",
        borderRadius: 12,
        background: "rgba(255,255,255,0.84)",
        color: palette.text,
        fontFamily: bodyFont,
        fontSize: compact ? 18 : 28,
        lineHeight: 1.3,
        fontWeight: 700,
        textAlign: "center",
        overflowWrap: "anywhere",
        wordBreak: "break-word"
      }}
    >
      {title}
    </div>
  </div>
);
