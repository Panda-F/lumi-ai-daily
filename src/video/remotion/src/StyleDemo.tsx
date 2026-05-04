import React from "react";
import { AbsoluteFill, Html5Video, Img, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { Icon, type IconName } from "./icons";
import { LUMI_COVER_GIF_SRC, LUMI_OUTRO_IMAGE_SRC, LUMI_OUTRO_VIDEO_SRC } from "./lumiAssets";
import { SegmentedProgressRail, type RailSegment } from "./SegmentedProgressRail";
import { palette, subtitlePanel } from "./theme";

export type StyleDemoVariant = "cover" | "opening" | "story" | "detail" | "outro";

type PageMode = "cover" | "opening" | "story_opener" | "story_visual" | "outro";

export type StyleDemoProps = {
  variant: StyleDemoVariant;
  openingCount?: number;
  openingPage?: number;
};

const editorialFont = '"Songti SC", "STSong", "Noto Serif SC", serif';
const bodyFont = '-apple-system, "PingFang SC", "Helvetica Neue", sans-serif';
const monoFont = '"SF Mono", "Menlo", monospace';

const shellPadding = 76;
const lumiAvatarSrc = LUMI_OUTRO_IMAGE_SRC;
const openingHeroSrc = staticFile(
  "generated/2026-04-15/media/02-02-11-cdn.prod.website-files.com-6914d00328fde4187dc9cdbe_claude-code_vs-code_preview-p-1600.webp"
);
const detailHeroSrc = staticFile("generated/2026-04-13/media/03-01-openai-enterprise-frontier-layer.png");

const ISSUE_QUOTE = {
  text: "预测未来最好的方式，就是亲手创造它。",
  author: "艾伦·凯 Alan Kay",
  locale: "zh-CN"
} as const;

const PAGE_MODE_BY_VARIANT: Record<StyleDemoVariant, PageMode> = {
  cover: "cover",
  opening: "opening",
  story: "story_opener",
  detail: "story_visual",
  outro: "outro"
};

const COVER_KEYWORDS = ["企业 AI", "工作流入口", "采购决策变化"] as const;

const OPENING_ITEMS = [
  "OpenAI 把企业 AI 推向统一控制层",
  "Anthropic 用真实工作流解释能力增长",
  "中国厂商继续把模型、搜索、Agent 打包卖",
  "企业采购开始从模型转向入口",
  "评估与治理重新回到购买前台",
  "工作流编排正在替代单点调用",
  "上下文层成为新的护城河",
  "默认入口权开始决定商业分发"
] as const;

const STORY_TITLE = "OpenAI 把企业 AI 推向统一控制层";
const DETAIL_TITLE = "它卖的不是模型，而是一整层企业入口。";
const DETAIL_EXPLAINER = "把产品界面、Agent、评估治理和上下文压到同一层后，企业买的就不是单点能力，而是统一入口。";
const DETAIL_NOTES = ["产品界面", "Agent 执行", "评估治理", "上下文层"] as const;
const OUTRO_TITLE = "Lumi 明天继续陪你看";

const openingLayoutProfile = (itemCount: number) => {
  if (itemCount <= 3) {
    return { fontSize: 40, rowPadding: 20, numberSize: 24, lineHeight: 1.2 };
  }
  if (itemCount <= 5) {
    return { fontSize: 36, rowPadding: 18, numberSize: 23, lineHeight: 1.2 };
  }
  if (itemCount === 6) {
    return { fontSize: 32, rowPadding: 14, numberSize: 22, lineHeight: 1.16 };
  }
  if (itemCount === 7) {
    return { fontSize: 30, rowPadding: 12, numberSize: 20, lineHeight: 1.12 };
  }
  return { fontSize: 26, rowPadding: 10, numberSize: 18, lineHeight: 1.08 };
};

const openingHeadlineSize = (itemCount: number) => {
  if (itemCount >= 8) return 76;
  if (itemCount >= 6) return 80;
  return 84;
};

const buildOpeningPages = (count: number) => {
  const items = OPENING_ITEMS.slice(0, Math.max(1, Math.min(count, OPENING_ITEMS.length)));
  const pages: string[][] = [];
  for (let index = 0; index < items.length; index += 8) {
    pages.push(items.slice(index, index + 8));
  }
  return pages.length ? pages : [OPENING_ITEMS.slice(0, 1)];
};

const buildProgressSegments = (mode: PageMode): RailSegment[] => {
  const states: Record<PageMode, number> = {
    cover: 0,
    opening: 1,
    story_opener: 2,
    story_visual: 3,
    outro: 4
  };
  const current = states[mode];
  const labels = ["封面", "开场", "入口争夺", "架构拆解", "结尾"];
  return labels.map((label, index) => ({
    key: `${label}-${index}`,
    label,
    state: index < current ? "past" : index === current ? "current" : "future"
  }));
};

const subtitleFontSize = (text: string) => {
  const length = [...text].length;
  if (length > 34) return 30;
  if (length > 24) return 34;
  return 38;
};

const SubtitleReference: React.FC<{ text: string }> = ({ text }) => {
  return (
    <div
      style={{
        position: "absolute",
        left: "50%",
        bottom: 54,
        transform: "translateX(-50%)",
        maxWidth: "calc(100% - 220px)",
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
            color: subtitlePanel.text,
            fontFamily: bodyFont,
            fontSize: subtitleFontSize(text),
            fontWeight: 400,
            lineHeight: 1.14,
            textAlign: "center",
            whiteSpace: "normal",
            overflow: "hidden",
            maxWidth: "100%"
          }}
        >
          {text}
        </div>
      </div>
    </div>
  );
};

const GlassPanel: React.FC<{ children: React.ReactNode; style?: React.CSSProperties }> = ({ children, style }) => {
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

const DarkStage: React.FC<{ children: React.ReactNode; style?: React.CSSProperties }> = ({ children, style }) => {
  return (
    <div
      style={{
        position: "relative",
        borderRadius: 8,
        background: "linear-gradient(180deg, rgba(255,255,255,0.94) 0%, rgba(252,247,251,0.98) 100%)",
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

const BigKeyword: React.FC<{ label: string }> = ({ label }) => {
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

const IssueQuoteBadge: React.FC<{ compact?: boolean; hero?: boolean; style?: React.CSSProperties }> = ({
  compact = false,
  hero = false,
  style
}) => {
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
        <Img src={lumiAvatarSrc} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
      </div>
      <div style={{ display: "grid", gap: 3, minWidth: 0 }}>
        <div
          style={{
            fontFamily: bodyFont,
            fontSize: bodySize,
            lineHeight: 1.32,
            color: palette.text,
            fontWeight: 600,
            overflow: "hidden"
          }}
        >
          {ISSUE_QUOTE.text}
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
            Lumi
          </div>
        </div>
      </div>
    </GlassPanel>
  );
};

const RichStrong: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <strong style={{ color: palette.text, fontWeight: 700 }}>{children}</strong>
);

const StoryCard: React.FC<{
  title: string;
  icon: IconName;
  children: React.ReactNode;
}> = ({ title, icon, children }) => {
  return (
    <GlassPanel
      style={{
        background: "linear-gradient(180deg, rgba(255,255,255,0.92) 0%, rgba(255,249,252,0.96) 100%)",
        padding: "24px 24px 26px",
        minHeight: 336
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
              width: 52,
              height: 52,
              borderRadius: 14,
              background: "rgba(244,114,182,0.12)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center"
            }}
          >
            <Icon name={icon} size={26} color={palette.deep} strokeWidth={1.9} />
          </div>
          <div
            style={{
              fontFamily: bodyFont,
              fontSize: 26,
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

const CardBodyText: React.FC<{ children: React.ReactNode; emphasis?: boolean }> = ({ children, emphasis = false }) => (
  <div
    style={{
      fontFamily: bodyFont,
      fontSize: 24,
      lineHeight: 1.48,
      color: palette.text,
      fontWeight: emphasis ? 600 : 500
    }}
  >
    {children}
  </div>
);

const BulletRow: React.FC<{ children: React.ReactNode }> = ({ children }) => (
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
        fontWeight: 500
      }}
    >
      {children}
    </div>
  </div>
);

const CoverScene: React.FC = () => {
  return (
    <div
      style={{
        height: "100%",
        display: "grid",
        gridTemplateColumns: "minmax(0, 0.98fr) minmax(560px, 1.02fr)",
        gap: 40
      }}
    >
      <div style={{ display: "grid", alignContent: "space-between" }}>
        <div style={{ display: "grid", gap: 26 }}>
          <div
            style={{
              width: 440,
              height: 22,
              borderRadius: 999,
              background: "linear-gradient(90deg, rgba(244,114,182,0.18) 0%, rgba(244,114,182,0.04) 100%)"
            }}
          />
          <div
            style={{
              fontFamily: editorialFont,
              fontSize: 104,
              lineHeight: 1.03,
              color: palette.text,
              fontWeight: 700,
              maxWidth: 860
            }}
          >
            企业买 AI 的方式
            <br />
            变了
          </div>
          <div
            style={{
              maxWidth: 720,
              fontFamily: bodyFont,
              fontSize: 34,
              lineHeight: 1.52,
              color: palette.textSoft
            }}
          >
            大模型厂商开始争夺的，不再只是能力本身，而是团队每天真正使用 AI 的入口。
          </div>
          <div
            style={{
              display: "flex",
              gap: 14,
              flexWrap: "wrap"
            }}
          >
            {COVER_KEYWORDS.map((label) => (
              <BigKeyword key={label} label={label} />
            ))}
          </div>
        </div>

        <div style={{ display: "grid", gap: 18, alignContent: "end" }}>
          <IssueQuoteBadge hero style={{ justifySelf: "start" }} />
        </div>
      </div>

      <div
        style={{
          position: "relative",
          display: "flex",
          alignItems: "center",
          justifyContent: "center"
        }}
      >
        <div
          style={{
            position: "absolute",
            width: 640,
            height: 640,
            borderRadius: 999,
            background: "radial-gradient(circle, rgba(244,114,182,0.12) 0%, rgba(192,132,252,0.06) 54%, transparent 72%)"
          }}
        />
        <div
          style={{
            position: "absolute",
            width: 560,
            height: 560,
            borderRadius: 999,
            border: "1px solid rgba(244,114,182,0.12)"
          }}
        />
        <div
          style={{
            width: 500,
            height: 500,
            borderRadius: 999,
            overflow: "hidden",
            border: "3px solid rgba(255,244,250,0.42)",
            boxShadow: "0 20px 44px rgba(236,72,153,0.12)"
          }}
        >
          <Img
            src={LUMI_COVER_GIF_SRC}
            style={{
              width: "100%",
              height: "100%",
              objectFit: "cover",
              objectPosition: "center"
            }}
          />
        </div>
      </div>
    </div>
  );
};

const OpeningScene: React.FC<{ openingCount: number; openingPage: number }> = ({ openingCount, openingPage }) => {
  const openingPages = buildOpeningPages(openingCount);
  const items = openingPages[Math.min(openingPage, openingPages.length - 1)];
  const profile = openingLayoutProfile(items.length);
  const titleSize = openingHeadlineSize(items.length);
  const sectionGap = items.length >= 7 ? 20 : 26;

  return (
    <div
      style={{
        height: "100%",
        display: "grid",
        gridTemplateColumns: "minmax(0, 1.04fr) minmax(420px, 0.96fr)",
        gap: 52
      }}
    >
      <div style={{ display: "grid", alignContent: "start", gap: sectionGap }}>
        <div
          style={{
            width: 460,
            height: 22,
            borderRadius: 999,
            background: "linear-gradient(90deg, rgba(244,114,182,0.18) 0%, rgba(244,114,182,0.04) 100%)"
          }}
        />
        <div
          style={{
            fontFamily: editorialFont,
            fontSize: titleSize,
            lineHeight: 1.07,
            color: palette.text,
            fontWeight: 700,
            maxWidth: 860
          }}
        >
          企业 AI，已经进入
          <br />
          “谁控制使用入口”阶段。
        </div>
        <GlassPanel style={{ padding: items.length >= 7 ? "6px 24px" : "8px 28px" }}>
          <div style={{ display: "grid" }}>
            {items.map((item, index) => (
              <div
                key={`${item}-${index}`}
                style={{
                  display: "grid",
                  gridTemplateColumns: "56px minmax(0, 1fr)",
                  gap: 16,
                  alignItems: "center",
                  padding: `${profile.rowPadding}px 0`,
                  borderBottom: index === items.length - 1 ? "none" : "1px solid rgba(31,28,30,0.08)"
                }}
              >
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontFamily: monoFont,
                    fontSize: profile.numberSize,
                    lineHeight: 1.1,
                    color: palette.deep,
                    fontWeight: 700
                  }}
                >
                  {String(index + 1).padStart(2, "0")}
                </div>
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    fontFamily: editorialFont,
                    fontSize: profile.fontSize,
                    lineHeight: profile.lineHeight,
                    color: palette.text,
                    fontWeight: 700
                  }}
                >
                  {item}
                </div>
              </div>
            ))}
          </div>
        </GlassPanel>
      </div>

      <div style={{ display: "grid" }}>
        <GlassPanel style={{ padding: 18 }}>
          <div
            style={{
              position: "absolute",
              inset: 18,
              borderRadius: 6,
              overflow: "hidden",
              background: "rgba(255,255,255,0.82)"
            }}
          >
            <Img
              src={openingHeroSrc}
              style={{
                width: "100%",
                height: "100%",
                objectFit: "cover",
                objectPosition: "center"
              }}
              />
          </div>
          <IssueQuoteBadge
            compact
            style={{
              position: "absolute",
              right: 18,
              bottom: 18,
              zIndex: 2
            }}
          />
        </GlassPanel>
      </div>
    </div>
  );
};

const StoryOpenerScene: React.FC = () => {
  return (
    <div
      style={{
        height: "100%",
        display: "grid",
        gridTemplateRows: "auto auto minmax(0, 1fr)",
        gap: 22
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "space-between",
          gap: 24
        }}
      >
        <div
          style={{
            width: 380,
            height: 22,
            borderRadius: 999,
            background: "linear-gradient(90deg, rgba(244,114,182,0.18) 0%, rgba(244,114,182,0.04) 100%)"
          }}
        />
        <IssueQuoteBadge compact />
      </div>

      <div
        style={{
          fontFamily: editorialFont,
          fontSize: 84,
          lineHeight: 1.08,
          color: palette.text,
          fontWeight: 700,
          maxWidth: 980
        }}
      >
        {STORY_TITLE}
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "minmax(0, 1.04fr) minmax(0, 0.98fr) minmax(0, 0.98fr)",
          gap: 18,
          alignItems: "stretch"
        }}
      >
        <StoryCard title="先看结论" icon="megaphone">
          <CardBodyText>
            这不是一次普通的产品更新，而是 OpenAI 在把 <RichStrong>模型能力</RichStrong> 重新包装成企业真正会买单的 <RichStrong>工作流入口</RichStrong>。
          </CardBodyText>
        </StoryCard>

        <StoryCard title="这次变了什么" icon="layers-3">
          <BulletRow>
            OpenAI 不再只强调 <RichStrong>模型性能</RichStrong>，而是把企业使用入口做成完整层级。
          </BulletRow>
          <BulletRow>
            <RichStrong>产品、Agent、评估、上下文</RichStrong> 被放进同一套叙事里。
          </BulletRow>
        </StoryCard>

        <StoryCard title="为什么值得盯" icon="shield-alert">
          <BulletRow>
            企业采购的核心，正在从 <RichStrong>谁最强</RichStrong> 转成 <RichStrong>谁最容易接入与治理</RichStrong>。
          </BulletRow>
          <BulletRow>
            接下来真正的竞争，是 <RichStrong>入口权、流程权、治理权</RichStrong>。
          </BulletRow>
        </StoryCard>
      </div>
    </div>
  );
};

const StoryVisualScene: React.FC = () => {
  return (
    <div
      style={{
        height: "100%",
        display: "grid",
        gridTemplateRows: "auto minmax(0, 1fr)",
        gap: 20
      }}
    >
      <div style={{ display: "grid", gap: 14 }}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 18
          }}
        >
          <div
            style={{
              minWidth: 0,
              fontFamily: editorialFont,
              fontSize: 48,
              lineHeight: 1.1,
              color: palette.text,
              fontWeight: 700,
              whiteSpace: "normal",
              overflow: "hidden"
            }}
          >
            {DETAIL_TITLE}
          </div>
          <IssueQuoteBadge compact style={{ flexShrink: 0 }} />
        </div>
        <div
          style={{
            fontFamily: bodyFont,
            fontSize: 24,
            lineHeight: 1.5,
            color: palette.textSoft,
            maxWidth: 980
          }}
        >
          {DETAIL_EXPLAINER}
        </div>
        <div
          style={{
            display: "flex",
            gap: 12,
            flexWrap: "wrap"
          }}
        >
          {DETAIL_NOTES.map((note) => (
            <div
              key={note}
              style={{
                display: "inline-flex",
                alignItems: "center",
                padding: "8px 14px",
                borderRadius: 8,
                background: "rgba(255,255,255,0.72)",
                border: "1px solid rgba(244,114,182,0.12)",
                fontFamily: bodyFont,
                fontSize: 18,
                lineHeight: 1.1,
                color: palette.textSoft,
                fontWeight: 600
              }}
            >
              {note}
            </div>
          ))}
        </div>
      </div>

      <GlassPanel style={{ padding: 26, background: "rgba(255,255,255,0.96)" }}>
        <div
          style={{
            position: "absolute",
            inset: 26,
            borderRadius: 6,
            background: "#FFFFFF",
            border: "1px solid rgba(31,28,30,0.06)"
          }}
        />
        <Img
          src={detailHeroSrc}
          style={{
            position: "absolute",
            inset: 44,
            width: "calc(100% - 88px)",
            height: "calc(100% - 88px)",
            objectFit: "contain"
          }}
        />
      </GlassPanel>
    </div>
  );
};

const OutroSceneDemo: React.FC = () => {
  return (
    <div
      style={{
        height: "100%",
        display: "grid",
        alignContent: "center",
        justifyItems: "center",
        gap: 28
      }}
    >
      <div
        style={{
          width: 460,
          height: 22,
          borderRadius: 999,
          background: "linear-gradient(90deg, rgba(244,114,182,0.18) 0%, rgba(244,114,182,0.04) 100%)"
        }}
      />
      <div
        style={{
          fontFamily: editorialFont,
          fontSize: 94,
          lineHeight: 1.06,
          color: palette.text,
          fontWeight: 700,
          textAlign: "center"
        }}
      >
        {OUTRO_TITLE}
      </div>
      <div
        style={{
          width: 276,
          height: 276,
          borderRadius: 999,
          overflow: "hidden",
          border: "6px solid rgba(255,255,255,0.82)",
          boxShadow: "0 18px 40px rgba(236,72,153,0.10)"
        }}
      >
        <Img
          src={LUMI_OUTRO_IMAGE_SRC}
          style={{
            width: "100%",
            height: "100%",
            objectFit: "cover"
          }}
        />
      </div>
      <div
        style={{
          width: 428,
          height: 240,
          borderRadius: 28,
          overflow: "hidden",
          border: "1px solid rgba(244,114,182,0.14)",
          background: "rgba(255,255,255,0.90)",
          boxShadow: "0 18px 40px rgba(236,72,153,0.10)"
        }}
      >
        <Html5Video
          src={LUMI_OUTRO_VIDEO_SRC}
          muted
          playsInline
          loop
          style={{
            width: "100%",
            height: "100%",
            objectFit: "cover",
            objectPosition: "center"
          }}
        />
      </div>
    </div>
  );
};

const DemoTopBar: React.FC<{ mode: PageMode }> = ({ mode }) => {
  return (
    <>
      <div
        style={{
          position: "absolute",
          left: shellPadding,
          right: shellPadding,
          top: 34,
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
          2026.04.16
        </div>
      </div>

      <SegmentedProgressRail
        segments={buildProgressSegments(mode)}
        style={{
          position: "absolute",
          left: shellPadding,
          right: shellPadding,
          top: 88
        }}
        labelSize={14}
      />
    </>
  );
};

const DemoShell: React.FC<{ variant: StyleDemoVariant; subtitle: string; children: React.ReactNode }> = ({
  variant,
  subtitle,
  children
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const entry = spring({
    frame,
    fps,
    config: { damping: 18, stiffness: 90, mass: 0.98 }
  });
  const rise = interpolate(entry, [0, 1], [24, 0]);
  const lightSweep = (frame * 0.22) % 180;
  const pageMode = PAGE_MODE_BY_VARIANT[variant];

  return (
    <AbsoluteFill style={{ backgroundColor: palette.bg, overflow: "hidden" }}>
      <div
        style={{
          position: "absolute",
          inset: 0,
          background: "linear-gradient(135deg, #FFF8F5 0%, #FFF1F7 54%, #F7F0FF 100%)"
        }}
      />
      <div
        style={{
          position: "absolute",
          top: -280,
          left: lightSweep - 220,
          width: 760,
          height: 1200,
          transform: "rotate(18deg)",
          background: "linear-gradient(180deg, rgba(255,255,255,0) 0%, rgba(255,255,255,0.18) 50%, rgba(255,255,255,0) 100%)"
        }}
      />
      <div
        style={{
          position: "absolute",
          top: 120,
          left: -90,
          width: 360,
          height: 360,
          borderRadius: 999,
          background: "radial-gradient(circle, rgba(244,114,182,0.15) 0%, rgba(244,114,182,0.06) 46%, transparent 70%)"
        }}
      />
      <div
        style={{
          position: "absolute",
          right: -120,
          bottom: -120,
          width: 420,
          height: 420,
          borderRadius: 999,
          background: "radial-gradient(circle, rgba(192,132,252,0.14) 0%, rgba(192,132,252,0.05) 48%, transparent 72%)"
        }}
      />

      <DemoTopBar mode={pageMode} />

      <div
        style={{
          position: "absolute",
          inset: `${146 + rise}px ${shellPadding}px 150px`,
          opacity: entry
        }}
      >
        {children}
      </div>

      <SubtitleReference text={subtitle} />
    </AbsoluteFill>
  );
};

export const StyleDemo: React.FC<StyleDemoProps> = ({ variant, openingCount = 6, openingPage = 0 }) => {
  if (variant === "opening") {
    return (
      <DemoShell variant={variant} subtitle="今天看三件事：入口、验证，以及一体化打法。">
        <OpeningScene openingCount={openingCount} openingPage={openingPage} />
      </DemoShell>
    );
  }

  if (variant === "story") {
    return (
      <DemoShell variant={variant} subtitle="OpenAI 正在把企业买 AI 的入口，往统一控制层上收。">
        <StoryOpenerScene />
      </DemoShell>
    );
  }

  if (variant === "detail") {
    return (
      <DemoShell variant={variant} subtitle="图里最关键的信号，是能力已经被重新打包成企业入口。">
        <StoryVisualScene />
      </DemoShell>
    );
  }

  if (variant === "outro") {
    return (
      <DemoShell variant={variant} subtitle="明早继续用更清楚的方式，把重要变化讲给你。">
        <OutroSceneDemo />
      </DemoShell>
    );
  }

  return (
    <DemoShell variant={variant} subtitle="企业买 AI，正在从买模型，变成买工作流入口。">
      <CoverScene />
    </DemoShell>
  );
};
