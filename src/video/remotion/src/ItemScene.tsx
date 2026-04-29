import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import {
  AccentBar,
  GlassPanel,
  IssueQuoteBadge,
  bodyFont,
  clampLabel,
  editorialFont,
  fallbackMediaArtwork,
  monoFont
} from "./LumiApprovedVisuals";
import { Icon, type IconName } from "./icons";
import { inferIcon, renderMedia } from "./helpers";
import { palette } from "./theme";
import { FitTextBlock } from "./TextFit";
import type { MediaAsset } from "./types";
import type { ItemScene as ItemSceneType, MediaKind } from "./types";

const uniq = (values: Array<string | null | undefined>) => {
  const seen = new Set<string>();
  return values
    .map((value) => (value || "").replace(/\s+/g, " ").trim())
    .filter((value) => {
      if (!value || seen.has(value)) {
        return false;
      }
      seen.add(value);
      return true;
    });
};

const sentence = (text?: string | null, fallback = "") => {
  const cleaned = (text || "").replace(/\s+/g, " ").trim();
  return cleaned || fallback;
};

const buildChangeBullets = (scene: ItemSceneType) =>
  uniq([
    ...(scene.fact_points || []),
    scene.content,
    scene.hook
  ]).slice(0, 2);

const buildWhyBullets = (scene: ItemSceneType) =>
  uniq([scene.interpretation, scene.outro, scene.takeaway, scene.quote]).slice(0, 2);

const collectMediaAssets = (scene: ItemSceneType) => {
  const deduped: MediaAsset[] = [];
  const seen = new Set<string>();
  const pushAsset = (src?: string | null, kind?: MediaKind | null, sourceDomain?: string | null) => {
    if (!src || seen.has(src)) {
      return;
    }
    seen.add(src);
    deduped.push({
      src,
      kind: kind || "image",
      source_domain: sourceDomain || scene.source_domain || "",
      priority: deduped.length
    });
  };

  pushAsset(scene.primary_media_src, scene.primary_media_kind, scene.source_domain);
  for (const asset of scene.media_assets || []) {
    pushAsset(asset.src, asset.kind, asset.source_domain);
  }
  return deduped;
};

const openingFramesFor = (scene: ItemSceneType) =>
  scene.shot_regions.find((shot) => shot.kind === "hook")?.end_frame ?? Math.max(96, Math.floor(scene.duration_frames * 0.48));

const noteFromBullet = (text: string) => clampLabel(text.replace(/[。！？；;，,]/g, " ").trim(), 12);

const screenCardIcon = (hint: string | undefined, fallback: IconName): IconName => {
  const text = (hint || "").toLowerCase();
  if (/[🎨🖼️✨]/u.test(text) || /创作|修图|firefly|photoshop|adobe/.test(text)) return "sparkles";
  if (/[🏛️🛂🔐🛡️]/u.test(text) || /安全|治理|合规|政府|政务|risk|guard|policy|fedramp/.test(text)) return "shield-alert";
  if (/[📚📖📄]/u.test(text) || /研究|资料|文档|benchmark|bench|paper|评测/.test(text)) return "file-text";
  if (/[📈📊]/u.test(text) || /图表|交付|dashboard/.test(text)) return "monitor";
  if (/[🔌🔗🧷]/u.test(text) || /入口|接口|连接|接进|link|api|connector|mcp/.test(text)) return "link-2";
  if (/[⚙️🧰🔧]/u.test(text) || /工具|环境|启动|复现|settings/.test(text)) return "toolbox";
  if (/[⏱️⏰]/u.test(text) || /等待|反馈|速度|冷启动/.test(text)) return "radio";
  if (/[💸🧮]/u.test(text) || /商业|合同|成本|账单|预算|enterprise|token/.test(text)) return "briefcase";
  if (/[🧪🔬]/u.test(text) || /实验|论文|测试|verified/.test(text)) return "flask";
  if (/[🧭🔍]/u.test(text) || /判断|验收|世界|规则|分清/.test(text)) return "compass";
  if (/[🪜]/u.test(text) || /系统|工作流|pipeline|workflow|层|分层/.test(text)) return "layers-3";
  if (/算力|云|aws|cloud|contract/.test(text)) return "cloud";
  return fallback || "sparkles";
};

const splitCardBody = (body: string, maxPoints = 3) => {
  const cleaned = body.replace(/\s+/g, " ").trim();
  const explicit = cleaned
    .split(/[；;]/)
    .map((part) => part.replace(/^[：:、,\s]+/, "").trim())
    .filter(Boolean);
  if (explicit.length >= 2) {
    return explicit.slice(0, maxPoints);
  }
  const sentenceParts = cleaned
    .split(/(?<=[。！？])\s*/)
    .map((part) => part.trim())
    .filter(Boolean);
  if (sentenceParts.length >= 2) {
    return sentenceParts.slice(0, maxPoints);
  }
  return [cleaned];
};

const EditorialInfoCard: React.FC<{
  card: { heading: string; body: string; icon_hint?: string | null };
  index: number;
  lead?: boolean;
  fallbackIcon: IconName;
}> = ({ card, index, lead = false, fallbackIcon }) => {
  const icon = screenCardIcon(card.icon_hint || undefined, fallbackIcon);
  const bodyPoints = splitCardBody(card.body, lead ? 3 : 2);
  const compactBody = card.body.replace(/\s+/g, " ").trim();
  const pointFontSize = lead ? (bodyPoints.length >= 3 ? 23 : 26) : 20;
  return (
    <GlassPanel
      style={{
        position: "relative",
        overflow: "hidden",
        minHeight: lead ? 364 : 172,
        padding: lead ? "28px 30px 30px" : "22px 24px",
        background: lead
          ? "linear-gradient(135deg, rgba(255,255,255,0.98) 0%, rgba(255,246,251,0.96) 56%, rgba(255,255,255,0.92) 100%)"
          : "linear-gradient(180deg, rgba(255,255,255,0.92) 0%, rgba(255,251,253,0.98) 100%)",
        border: lead ? "1px solid rgba(236,72,153,0.22)" : "1px solid rgba(31,28,30,0.07)",
        boxShadow: lead ? "0 22px 50px rgba(236,72,153,0.12)" : "0 12px 26px rgba(31,28,30,0.045)"
      }}
    >
      {lead ? (
        <div
          style={{
            position: "absolute",
            right: -18,
            top: 24,
            width: 210,
            height: 86,
            borderRadius: 8,
            background: "linear-gradient(135deg, rgba(244,114,182,0.13), rgba(192,132,252,0.05))",
            transform: "rotate(10deg)"
          }}
        />
      ) : null}
      <div
        style={{
          position: "absolute",
          left: 0,
          top: lead ? 26 : 20,
          bottom: lead ? 26 : 20,
          width: lead ? 5 : 3,
          borderRadius: 8,
          background: lead ? palette.deep : "rgba(244,114,182,0.45)"
        }}
      />
      <div
        style={{
          display: "grid",
          gridTemplateRows: "auto minmax(0, 1fr) auto",
          gap: lead ? 24 : 14,
          height: "100%",
          position: "relative",
          zIndex: 1
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 16
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: lead ? 16 : 12,
              minWidth: 0
            }}
          >
            <div
              style={{
                width: lead ? 58 : 44,
                height: lead ? 58 : 44,
                borderRadius: 8,
                background: lead ? "rgba(244,114,182,0.14)" : "rgba(244,114,182,0.08)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                flexShrink: 0
              }}
            >
              <Icon name={icon} size={lead ? 30 : 23} color={palette.deep} strokeWidth={1.9} />
            </div>
            <div
              style={{
                fontFamily: bodyFont,
                fontSize: lead ? 32 : 25,
                lineHeight: lead ? 1.16 : 1.2,
                color: palette.text,
                fontWeight: 760,
                overflowWrap: "anywhere",
                wordBreak: "break-word"
              }}
            >
              {card.heading}
            </div>
          </div>
          <div
            style={{
              flexShrink: 0,
              fontFamily: monoFont,
              fontSize: lead ? 18 : 15,
              lineHeight: 1,
              color: lead ? palette.deep : palette.muted,
              fontWeight: 700,
              letterSpacing: 0,
              padding: lead ? "8px 10px" : "6px 8px",
              borderRadius: 8,
              background: lead ? "rgba(244,114,182,0.10)" : "rgba(31,28,30,0.04)",
              border: lead ? "1px solid rgba(244,114,182,0.16)" : "1px solid rgba(31,28,30,0.06)"
            }}
          >
            {String(index + 1).padStart(2, "0")}
          </div>
        </div>
        <div
          style={{
            fontFamily: bodyFont,
            fontSize: pointFontSize,
            lineHeight: lead ? 1.42 : 1.34,
            color: lead ? palette.text : palette.textSoft,
            fontWeight: lead ? 620 : 540,
            overflowWrap: "anywhere",
            wordBreak: "break-word",
            maxWidth: lead ? 660 : 520,
            display: "flex",
            flexDirection: "column",
            gap: lead ? 12 : 8,
            alignContent: "start",
            alignItems: "start"
          }}
        >
          {(lead ? bodyPoints : bodyPoints.length > 1 ? bodyPoints : [compactBody]).map((point, pointIndex) => (
            <div
              key={`${point}-${pointIndex}`}
              style={{
                display: "grid",
                gridTemplateColumns: lead ? "20px minmax(0, 1fr)" : "16px minmax(0, 1fr)",
                gap: lead ? 11 : 8,
                alignItems: "start",
                width: "100%"
              }}
            >
              <span
                style={{
                  width: lead ? 10 : 8,
                  height: lead ? 10 : 8,
                  borderRadius: 3,
                  background: pointIndex === 0 ? palette.deep : "rgba(244,114,182,0.46)",
                  marginTop: lead ? 12 : 9,
                  boxShadow: pointIndex === 0 ? "0 0 0 4px rgba(244,114,182,0.10)" : "none"
                }}
              />
              <span style={{ color: lead && pointIndex > 0 ? palette.textSoft : undefined }}>{point}</span>
            </div>
          ))}
        </div>
        {lead ? (
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 0.72fr 0.38fr",
              gap: 8,
              alignItems: "center",
              opacity: 0.72
            }}
          >
            <div style={{ height: 4, borderRadius: 8, background: "rgba(236,72,153,0.40)" }} />
            <div style={{ height: 4, borderRadius: 8, background: "rgba(236,72,153,0.22)" }} />
            <div style={{ height: 4, borderRadius: 8, background: "rgba(236,72,153,0.12)" }} />
          </div>
        ) : null}
      </div>
    </GlassPanel>
  );
};

export const ItemScene: React.FC<{
  scene: ItemSceneType;
  lumiAvatarSrc?: string | null;
  issueQuoteText?: string | null;
  issueQuoteAuthor?: string | null;
}> = ({ scene, lumiAvatarSrc, issueQuoteText, issueQuoteAuthor }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const sceneOpacity = interpolate(frame, [0, 8, scene.duration_frames - 12, scene.duration_frames], [0, 1, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp"
  });
  const openerEnd = openingFramesFor(scene);
  const openerOpacity = interpolate(frame, [0, Math.max(openerEnd - 12, 1), openerEnd + 8], [1, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp"
  });
  const detailOpacity = interpolate(frame, [openerEnd + 4, openerEnd + 22], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp"
  });
  const openerIn = spring({
    frame,
    fps,
    config: { damping: 16, stiffness: 112, mass: 0.96 }
  });
  const detailIn = spring({
    frame: Math.max(frame - openerEnd, 0),
    fps,
    config: { damping: 16, stiffness: 112, mass: 0.94 }
  });
  const changeBullets = buildChangeBullets(scene);
  const whyBullets = buildWhyBullets(scene);
  const mediaAssets = collectMediaAssets(scene);
  const visualFrame = Math.max(0, frame - openerEnd);
  const visualDuration = Math.max(1, scene.duration_frames - openerEnd);
  const visualAssetIndex =
    mediaAssets.length > 1 ? Math.min(mediaAssets.length - 1, Math.floor((visualFrame / visualDuration) * mediaAssets.length)) : 0;
  const activeAsset = mediaAssets[visualAssetIndex] ?? null;
  const storyTitle = sentence(scene.display_title || scene.title || scene.short_title, "AI 速递");
  const detailTitle = sentence(scene.display_title || scene.title || scene.short_title, storyTitle);
  const detailSummary = sentence(scene.interpretation || scene.takeaway || scene.content, scene.takeaway);
  const detailNotes = uniq([
    ...changeBullets.map(noteFromBullet),
    ...whyBullets.map(noteFromBullet),
    noteFromBullet(scene.source_domain || "")
  ]).slice(0, 4);
  const fallbackIcon = (scene.display_icon as IconName | null) || inferIcon(scene.title, scene.item_kind);
  const screenCards = (scene.screen_cards || []).filter((card) => card.heading && card.body).slice(0, 3);

  return (
    <AbsoluteFill style={{ opacity: sceneOpacity, overflow: "hidden" }}>
      <div
        style={{
          position: "absolute",
          inset: "138px 76px 134px"
        }}
      >
        <div
          style={{
            position: "absolute",
            inset: 0,
            display: "grid",
            gridTemplateRows: "auto auto minmax(0, 1fr)",
            gap: 22,
            opacity: openerOpacity,
            transform: `translateY(${interpolate(openerIn, [0, 1], [22, 0])}px)`
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
            <AccentBar width={380} />
            <IssueQuoteBadge compact avatarSrc={lumiAvatarSrc} text={issueQuoteText || undefined} author={issueQuoteAuthor || undefined} />
          </div>

          <div
            style={{
              display: "grid",
              gridTemplateColumns: "64px minmax(0, 1fr)",
              gap: 18,
              alignItems: "start",
              maxWidth: 1540
            }}
          >
            <div
              style={{
                width: 52,
                height: 52,
                borderRadius: 12,
                background: "rgba(244,114,182,0.10)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                marginTop: 6
              }}
            >
              <Icon name={fallbackIcon} size={28} color={palette.deep} strokeWidth={1.9} />
            </div>
            <FitTextBlock
              text={storyTitle}
              maxWidth={1440}
              maxFontSize={76}
              minFontSize={42}
              maxLines={2}
              lineHeight={1.08}
              style={{
                fontFamily: editorialFont,
                color: palette.text,
                fontWeight: 700
              }}
            />
          </div>

          <div
            style={{
              display: "grid",
              gridTemplateColumns: "minmax(0, 1.16fr) minmax(0, 0.92fr)",
              gridTemplateRows: "minmax(0, 1fr)",
              gap: 18,
              alignItems: "stretch",
              minHeight: 372
            }}
          >
            {screenCards[0] ? (
              <EditorialInfoCard card={screenCards[0]} index={0} lead fallbackIcon={fallbackIcon} />
            ) : null}
            <div
              style={{
                display: "grid",
                gridTemplateRows: "1fr 1fr",
                gap: 18,
                minHeight: 0
              }}
            >
              {screenCards.slice(1, 3).map((card, index) => (
                <EditorialInfoCard key={`${card.heading}-${index + 1}`} card={card} index={index + 1} fallbackIcon={fallbackIcon} />
              ))}
            </div>
          </div>
        </div>

        <div
          style={{
            position: "absolute",
            inset: 0,
            display: "grid",
            gridTemplateRows: "auto minmax(0, 1fr)",
            gap: 20,
            opacity: detailOpacity,
            transform: `translateY(${interpolate(detailIn, [0, 1], [26, 0])}px)`
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
                  display: "grid",
                  gridTemplateColumns: "46px minmax(0, 1fr)",
                  gap: 14,
                  alignItems: "start"
                }}
              >
                <div
                  style={{
                    width: 42,
                    height: 42,
                    borderRadius: 10,
                    background: "rgba(244,114,182,0.10)",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    marginTop: 4
                  }}
                >
                  <Icon name={fallbackIcon} size={22} color={palette.deep} strokeWidth={1.9} />
                </div>
                <FitTextBlock
                  text={detailTitle}
                  maxWidth={1120}
                  maxFontSize={52}
                  minFontSize={30}
                  maxLines={2}
                  lineHeight={1.1}
                  style={{
                    fontFamily: editorialFont,
                    color: palette.text,
                    fontWeight: 700
                  }}
                />
              </div>
              <IssueQuoteBadge compact avatarSrc={lumiAvatarSrc} text={issueQuoteText || undefined} author={issueQuoteAuthor || undefined} style={{ flexShrink: 0 }} />
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
              {detailSummary}
            </div>
            {detailNotes.length ? (
              <div
                style={{
                  display: "flex",
                  gap: 12,
                  flexWrap: "wrap"
                }}
              >
                {detailNotes.map((note) => (
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
            ) : null}
          </div>

          <GlassPanel style={{ padding: 26, background: "rgba(255,255,255,0.96)" }}>
            <div
              style={{
                position: "absolute",
                inset: 26,
                borderRadius: 6,
                background: "#FFFFFF",
                border: "1px solid rgba(31,28,30,0.06)",
                overflow: "hidden"
              }}
            >
              <div
                style={{
                  position: "absolute",
                  inset: 18,
                  borderRadius: 6,
                  overflow: "hidden",
                  background: "#FFFFFF",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center"
                }}
              >
                {activeAsset?.src ? (
                  renderMedia(activeAsset.src, activeAsset.kind, "contain")
                ) : (
                  fallbackMediaArtwork({ title: detailTitle, icon: fallbackIcon })
                )}
              </div>
            </div>
          </GlassPanel>
        </div>
      </div>
    </AbsoluteFill>
  );
};
