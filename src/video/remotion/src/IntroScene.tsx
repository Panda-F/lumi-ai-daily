import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { AccentBar, BigKeyword, GlassPanel, IssueQuoteBadge, bodyFont, editorialFont } from "./LumiApprovedVisuals";
import { fallbackMediaArtwork } from "./LumiApprovedVisuals";
import { renderMedia } from "./helpers";
import { Icon, type IconName } from "./icons";
import { palette } from "./theme";
import { FitTextBlock } from "./TextFit";
import type { IntroScene as IntroSceneType } from "./types";

const splitAgendaPages = (items: Array<{ index: number; label: string; icon?: string | null }>, pageSize = 8) => {
  const sanitized = items
    .map((item) => ({
      ...item,
      label: item.label.replace(/^[\d.、\-•\s]+/u, "").trim()
    }))
    .filter((item) => item.label);
  const pages: Array<Array<{ index: number; label: string; icon?: string | null }>> = [];
  for (let index = 0; index < sanitized.length; index += pageSize) {
    pages.push(sanitized.slice(index, index + pageSize));
  }
  return pages.length ? pages : [[{ index: 1, label: "今日 AI 速递", icon: "sparkles" }]];
};

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
    return { fontSize: 28, rowPadding: 10, numberSize: 19, lineHeight: 1.08 };
  }
  return { fontSize: 24, rowPadding: 8, numberSize: 17, lineHeight: 1.02 };
};

const chooseLeadTitle = (title?: string | null, fallback = "今日 AI 速递") => {
  const cleaned = (title || "").replace(/\s+/g, " ").trim();
  return cleaned || fallback;
};

const pickHeroIcon = (title: string): IconName => {
  if (/Agent|工作流|入口|控制/i.test(title)) return "layers-3";
  if (/研究|论文|模型/i.test(title)) return "masks";
  if (/安全|治理|风险/i.test(title)) return "shield-alert";
  return "sparkles";
};

export const IntroScene: React.FC<{
  scene: IntroSceneType;
  lumiAvatarSrc?: string | null;
  issueQuoteText?: string | null;
  issueQuoteAuthor?: string | null;
  primaryHook?: string | null;
}> = ({ scene, lumiAvatarSrc, issueQuoteText, issueQuoteAuthor, primaryHook }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const titleCut = scene.shot_regions.find((shot) => shot.kind === "intro_title")?.end_frame ?? Math.round(scene.duration_frames * 0.32);
  const openingStart = Math.max(0, titleCut - 8);
  const openingPages = splitAgendaPages(scene.opening_items || []);
  const openingFrame = Math.max(0, frame - openingStart);
  const openingDuration = Math.max(1, scene.duration_frames - openingStart);
  const openingPageDuration = Math.max(1, Math.floor(openingDuration / openingPages.length));
  const openingPageIndex = Math.min(openingPages.length - 1, Math.floor(openingFrame / openingPageDuration));
  const openingItems = openingPages[openingPageIndex];
  const openingProfile = openingLayoutProfile(openingItems.length);
  const coverTitle = chooseLeadTitle(primaryHook || scene.lead_title || scene.title);
  const openingTitle = chooseLeadTitle(primaryHook || scene.transition || scene.lead_title);
  const coverSummary = chooseLeadTitle(scene.opening || scene.agenda, "今天的 AI 速递开始。");
  const coverIn = spring({
    frame,
    fps,
    config: { damping: 16, stiffness: 110, mass: 0.96 }
  });
  const openingIn = spring({
    frame: Math.max(frame - openingStart, 0),
    fps,
    config: { damping: 16, stiffness: 112, mass: 0.94 }
  });
  const coverOpacity = interpolate(frame, [0, Math.max(titleCut - 16, 1), titleCut + 8], [1, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp"
  });
  const openingOpacity = interpolate(frame, [Math.max(openingStart - 10, 0), openingStart + 18], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp"
  });
  const lumiIntroSrc = scene.lumi_intro_src || scene.lead_media_src || null;
  const lumiIntroKind = scene.lumi_intro_kind || scene.primary_media_kind || null;
  const leadMediaSrc = scene.primary_media_src || scene.lead_media_src || null;
  const leadMediaKind = scene.primary_media_kind || null;
  const heroIcon = pickHeroIcon(scene.lead_title || openingTitle);

  return (
    <AbsoluteFill style={{ overflow: "hidden" }}>
      <div
        style={{
          position: "absolute",
          inset: "138px 76px 134px",
          overflow: "hidden"
        }}
      >
        <div
          style={{
            position: "absolute",
            inset: 0,
            display: "grid",
            gridTemplateColumns: "minmax(0, 0.98fr) minmax(560px, 1.02fr)",
            gap: 40,
            opacity: coverOpacity,
            transform: `translateY(${interpolate(coverIn, [0, 1], [20, 0])}px)`
          }}
        >
          <div style={{ display: "grid", alignContent: "space-between" }}>
            <div style={{ display: "grid", gap: 26 }}>
              <AccentBar width={440} />
              <FitTextBlock
                text={coverTitle}
                maxWidth={980}
                maxFontSize={104}
                minFontSize={54}
                maxLines={3}
                lineHeight={1.04}
                style={{
                  fontFamily: editorialFont,
                  color: palette.text,
                  fontWeight: 700,
                  maxWidth: 980
                }}
              />
              <div
                style={{
                  maxWidth: 720,
                  fontFamily: bodyFont,
                  fontSize: 32,
                  lineHeight: 1.52,
                  color: palette.textSoft
                }}
              >
                {coverSummary}
              </div>
              <div
                style={{
                  display: "flex",
                  gap: 14,
                  flexWrap: "wrap"
                }}
              >
                {(scene.trend_words || []).slice(0, 3).map((label) => (
                  <BigKeyword key={label} label={label} />
                ))}
              </div>
            </div>

            <IssueQuoteBadge
              hero
              avatarSrc={lumiAvatarSrc}
              text={issueQuoteText || undefined}
              author={issueQuoteAuthor || undefined}
              style={{ justifySelf: "start", maxWidth: 680 }}
            />
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
                width: 700,
                height: 700,
                borderRadius: 999,
                background:
                  "radial-gradient(circle, rgba(244,114,182,0.14) 0%, rgba(192,132,252,0.06) 56%, transparent 74%)"
              }}
            />
            <div
              style={{
                position: "absolute",
                width: 590,
                height: 590,
                borderRadius: 999,
                border: "1px solid rgba(244,114,182,0.12)"
              }}
            />
              <div
                style={{
                  width: 540,
                  height: 540,
                  borderRadius: 999,
                  overflow: "hidden",
                  boxShadow: "0 20px 44px rgba(236,72,153,0.12)"
                }}
              >
              {lumiIntroSrc ? renderMedia(lumiIntroSrc, lumiIntroKind, "cover") : fallbackMediaArtwork({ title: coverTitle, icon: heroIcon })}
            </div>
          </div>
        </div>

        <div
          style={{
            position: "absolute",
            inset: 0,
            display: "grid",
            gridTemplateColumns: "minmax(0, 1.04fr) minmax(420px, 0.96fr)",
            gap: 52,
            opacity: openingOpacity,
            transform: `translateY(${interpolate(openingIn, [0, 1], [26, 0])}px)`
          }}
        >
          <div style={{ display: "grid", alignContent: "start", gap: openingItems.length >= 7 ? 14 : 24 }}>
            <AccentBar width={460} />
            <FitTextBlock
              text={openingTitle}
              maxWidth={980}
              maxFontSize={82}
              minFontSize={44}
              maxLines={3}
              lineHeight={1.08}
              style={{
                fontFamily: editorialFont,
                color: palette.text,
                fontWeight: 700,
                maxWidth: 980
              }}
            />
            <GlassPanel style={{ padding: openingItems.length >= 7 ? "2px 22px" : "8px 28px" }}>
              <div style={{ display: "grid" }}>
                {openingItems.map((item, index) => (
                  <div
                    key={`${item.label}-${index}`}
                    style={{
                      display: "grid",
                      gridTemplateColumns: "64px 42px minmax(0, 1fr)",
                      gap: 16,
                      alignItems: "center",
                      padding: `${openingProfile.rowPadding}px 0`,
                      borderBottom: index === openingItems.length - 1 ? "none" : "1px solid rgba(31,28,30,0.08)"
                    }}
                  >
                    <div
                      style={{
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        fontFamily: '"SF Mono", "Menlo", monospace',
                        fontSize: openingProfile.numberSize,
                        lineHeight: 1.1,
                        color: palette.deep,
                        fontWeight: 700
                      }}
                    >
                      {String(openingPageIndex * 8 + index + 1).padStart(2, "0")}
                    </div>
                    <div
                      style={{
                        width: 36,
                        height: 36,
                        borderRadius: 8,
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        background: "rgba(244,114,182,0.10)"
                      }}
                    >
                      <Icon name={(item.icon || "sparkles") as IconName} size={20} color={palette.deep} strokeWidth={1.9} />
                    </div>
                    <FitTextBlock
                      text={item.label}
                      maxWidth={760}
                      maxFontSize={openingProfile.fontSize}
                      minFontSize={22}
                      maxLines={2}
                      lineHeight={openingProfile.lineHeight}
                      style={{
                        fontFamily: editorialFont,
                        color: palette.text,
                        fontWeight: 700,
                        minHeight: openingProfile.fontSize * openingProfile.lineHeight
                      }}
                    />
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
                  background: "rgba(255,255,255,0.90)"
                }}
              >
                {leadMediaSrc ? (
                  renderMedia(leadMediaSrc, leadMediaKind, "cover")
                ) : (
                  fallbackMediaArtwork({ title: openingTitle, icon: heroIcon })
                )}
              </div>
              <IssueQuoteBadge
                compact
                avatarSrc={lumiAvatarSrc}
                text={issueQuoteText || undefined}
                author={issueQuoteAuthor || undefined}
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
      </div>
    </AbsoluteFill>
  );
};
