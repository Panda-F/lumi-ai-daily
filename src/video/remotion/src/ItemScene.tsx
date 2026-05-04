import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import {
  AccentBar,
  GlassPanel,
  bodyFont,
  editorialFont,
  fallbackMediaArtwork
} from "./LumiApprovedVisuals";
import { Icon, type IconName } from "./icons";
import { inferIcon, renderMedia } from "./helpers";
import { palette } from "./theme";
import { FitTextBlock } from "./TextFit";
import type { MediaAsset, ScreenCard } from "./types";
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

const visualUnits = (text: string) =>
  Array.from(text || "").reduce((total, char) => total + (/[\u4e00-\u9fff]/.test(char) ? 1 : 0.55), 0);

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

const splitCardBody = (card: ScreenCard, maxPoints = 3) => {
  const directPoints = uniq(card.points || []).slice(0, maxPoints);
  if (directPoints.length) {
    return directPoints;
  }
  const body = card.body || "";
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

const genericCardHeadings = new Set(["事实锚点", "人的影响", "继续观察", "观看理由", "判断框架"]);

const displayCardHeading = (card: ScreenCard, index: number) => {
  const heading = sentence(card.heading);
  if (heading && !genericCardHeadings.has(heading)) {
    return heading;
  }
  const emphasis = sentence(card.emphasis);
  if (index === 0) {
    return emphasis || "变化已经落地";
  }
  if (index === 1) {
    return "谁先感到代价";
  }
  return "明天该盯哪里";
};

const cardKicker = (index: number) => {
  if (index === 0) return "事实变化";
  if (index === 1) return "人的代价";
  return "继续观察";
};

const ParticleField: React.FC<{ density?: number; opacity?: number }> = ({ density = 26, opacity = 1 }) => {
  const frame = useCurrentFrame();
  return (
    <div style={{ position: "absolute", inset: 0, overflow: "hidden", pointerEvents: "none", opacity }}>
      {Array.from({ length: density }).map((_, index) => {
        const x = 5 + ((index * 37) % 91);
        const y = 8 + ((index * 53) % 82);
        const drift = interpolate((frame + index * 9) % 140, [0, 70, 140], [-8, 10, -8], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp"
        });
        const glow = interpolate((frame + index * 13) % 120, [0, 60, 120], [0.18, 0.58, 0.18], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp"
        });
        const size = index % 5 === 0 ? 7 : index % 3 === 0 ? 5 : 3;
        return (
          <div
            key={index}
            style={{
              position: "absolute",
              left: `${x}%`,
              top: `${y}%`,
              width: size,
              height: size,
              borderRadius: 999,
              background: index % 2 ? "rgba(244,114,182,0.48)" : "rgba(255,199,219,0.72)",
              opacity: glow,
              transform: `translate3d(${drift}px, ${drift * 0.42}px, 0)`,
              boxShadow: "0 0 18px rgba(244,114,182,0.26)"
            }}
          />
        );
      })}
    </div>
  );
};

const EditorialInfoCard: React.FC<{
  card: ScreenCard;
  index: number;
  lead?: boolean;
  fallbackIcon: IconName;
}> = ({ card, index, lead = false, fallbackIcon }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const icon = screenCardIcon(card.icon_hint || undefined, fallbackIcon);
  const bodyPoints = splitCardBody(card, lead ? 3 : 2);
  const pointWeight = bodyPoints.reduce((total, point) => total + visualUnits(point), 0);
  const pointFontSize = lead
    ? pointWeight > 120
      ? 29
      : pointWeight > 96
        ? 32
        : bodyPoints.length >= 3
          ? 35
          : 40
    : pointWeight > 82
      ? 24
      : pointWeight > 60
        ? 27
        : 32;
  const heading = displayCardHeading(card, index);
  const emphasis = sentence(card.emphasis, index === 0 ? "关键变化" : index === 1 ? "人的处境" : "后续信号");
  const cardIn = spring({
    frame: Math.max(frame - index * 5, 0),
    fps,
    config: { damping: 17, stiffness: 126, mass: 0.82 }
  });
  return (
    <GlassPanel
      style={{
        position: "relative",
        overflow: "hidden",
        minHeight: lead ? 468 : 224,
        padding: lead ? "42px 46px 36px" : "32px 32px 28px",
        opacity: interpolate(cardIn, [0, 1], [0.86, 1]),
        transform: `perspective(980px) rotateX(${lead ? "-1.2deg" : "0.7deg"}) rotateY(${lead ? "1.6deg" : "-1deg"}) translateY(${interpolate(cardIn, [0, 1], [18, 0])}px) scale(${interpolate(cardIn, [0, 1], [0.985, 1])})`,
        background: lead
          ? "radial-gradient(circle at 78% 10%, rgba(244,114,182,0.16), transparent 32%), linear-gradient(135deg, rgba(255,255,255,0.98) 0%, rgba(255,246,251,0.97) 50%, rgba(255,255,255,0.93) 100%)"
          : "radial-gradient(circle at 82% 4%, rgba(244,114,182,0.12), transparent 32%), linear-gradient(180deg, rgba(255,255,255,0.95) 0%, rgba(255,250,253,0.98) 100%)",
        border: lead ? "1px solid rgba(236,72,153,0.25)" : "1px solid rgba(31,28,30,0.08)",
        boxShadow: lead
          ? "0 32px 70px rgba(236,72,153,0.16), inset 0 1px 0 rgba(255,255,255,0.95)"
          : "0 18px 40px rgba(31,28,30,0.06), inset 0 1px 0 rgba(255,255,255,0.9)"
      }}
    >
      <ParticleField density={lead ? 18 : 10} opacity={lead ? 0.74 : 0.44} />
      <div
        style={{
          position: "absolute",
          inset: 0,
          background:
            "linear-gradient(90deg, rgba(236,72,153,0.045) 1px, transparent 1px), linear-gradient(180deg, rgba(31,28,30,0.032) 1px, transparent 1px)",
          backgroundSize: lead ? "42px 42px" : "34px 34px",
          opacity: lead ? 0.46 : 0.32,
          maskImage: "linear-gradient(135deg, rgba(0,0,0,0.82), rgba(0,0,0,0.18))"
        }}
      />
      {lead ? (
        <div
          style={{
            position: "absolute",
            right: -34,
            top: 34,
            width: 260,
            height: 104,
            borderRadius: 8,
            background: "linear-gradient(135deg, rgba(244,114,182,0.14), rgba(255,214,231,0.18))",
            transform: "rotate(10deg)",
            boxShadow: "0 22px 48px rgba(244,114,182,0.10)"
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
            gap: lead ? 26 : 18,
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
                gap: lead ? 18 : 13,
                minWidth: 0
              }}
            >
            <div
              style={{
                width: lead ? 72 : 52,
                height: lead ? 72 : 52,
                borderRadius: 8,
                background: lead ? "linear-gradient(135deg, rgba(244,114,182,0.18), rgba(255,214,231,0.36))" : "rgba(244,114,182,0.10)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                flexShrink: 0,
                boxShadow: lead ? "0 14px 26px rgba(244,114,182,0.12)" : "none"
              }}
            >
              <Icon name={icon} size={lead ? 36 : 26} color={palette.deep} strokeWidth={1.9} />
            </div>
            <div
              style={{
                fontFamily: editorialFont,
                fontSize: lead ? 56 : 40,
                lineHeight: lead ? 1.12 : 1.16,
                color: palette.text,
                fontWeight: 760,
                overflowWrap: "anywhere",
                wordBreak: "break-word"
              }}
            >
              {heading}
            </div>
          </div>
          <div
            style={{
              flexShrink: 0,
              fontFamily: bodyFont,
              fontSize: lead ? 22 : 18,
              lineHeight: 1.05,
              color: lead ? palette.deep : palette.muted,
              fontWeight: 760,
              letterSpacing: 0,
              padding: lead ? "10px 14px" : "8px 11px",
              borderRadius: 8,
              background: lead ? "rgba(244,114,182,0.10)" : "rgba(31,28,30,0.04)",
              border: lead ? "1px solid rgba(244,114,182,0.16)" : "1px solid rgba(31,28,30,0.06)",
              maxWidth: lead ? 168 : 132,
              overflowWrap: "anywhere",
              wordBreak: "break-word",
              textAlign: "center"
            }}
          >
            {emphasis}
          </div>
        </div>
        <div
          style={{
            fontFamily: bodyFont,
            fontSize: pointFontSize,
            lineHeight: lead ? 1.26 : 1.22,
            color: lead ? palette.text : palette.textSoft,
            fontWeight: lead ? 620 : 540,
            overflowWrap: "anywhere",
            wordBreak: "break-word",
            maxWidth: lead ? 840 : 600,
            display: "flex",
            flexDirection: "column",
            gap: lead ? 17 : 11,
            alignContent: "start",
            alignItems: "start"
          }}
        >
          {bodyPoints.map((point, pointIndex) => (
            <div
              key={`${point}-${pointIndex}`}
              style={{
                display: "grid",
                gridTemplateColumns: lead ? "28px minmax(0, 1fr)" : "22px minmax(0, 1fr)",
                gap: lead ? 14 : 10,
                alignItems: "start",
                width: "100%"
              }}
            >
              <span
                style={{
                  width: lead ? 14 : 10,
                  height: lead ? 14 : 10,
                  borderRadius: 999,
                  background: pointIndex === 0 ? palette.deep : "rgba(244,114,182,0.46)",
                  marginTop: lead ? 13 : 10,
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
              display: "flex",
              justifyContent: "space-between",
              gap: 12,
              alignItems: "center",
              opacity: 0.78
            }}
          >
            <div
              style={{
                fontFamily: bodyFont,
                fontSize: 18,
                color: palette.muted,
                fontWeight: 700
              }}
            >
              {cardKicker(index)}
            </div>
            <div style={{ flex: 1, height: 4, borderRadius: 8, background: "linear-gradient(90deg, rgba(236,72,153,0.40), rgba(236,72,153,0.06))" }} />
          </div>
        ) : null}
      </div>
    </GlassPanel>
  );
};

export const ItemScene: React.FC<{
  scene: ItemSceneType;
}> = ({ scene }) => {
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
  const mediaAssets = collectMediaAssets(scene);
  const visualFrame = Math.max(0, frame - openerEnd);
  const visualDuration = Math.max(1, scene.duration_frames - openerEnd);
  const visualAssetIndex =
    mediaAssets.length > 1 ? Math.min(mediaAssets.length - 1, Math.floor((visualFrame / visualDuration) * mediaAssets.length)) : 0;
  const activeAsset = mediaAssets[visualAssetIndex] ?? null;
  const storyTitle = sentence(scene.display_title || scene.title || scene.short_title, "AI 速递");
  const detailTitle = sentence(scene.display_title || scene.title || scene.short_title, storyTitle);
  const detailSummary = sentence(scene.media_summary || scene.interpretation || scene.takeaway || scene.content, scene.takeaway);
  const fallbackIcon = (scene.display_icon as IconName | null) || inferIcon(scene.title, scene.item_kind);
  const screenCards = (scene.screen_cards || [])
    .filter((card) => card.heading && (card.body || (card.points || []).length))
    .slice(0, 3);

  return (
    <AbsoluteFill style={{ opacity: sceneOpacity, overflow: "hidden" }}>
      <ParticleField density={36} opacity={0.24} />
      <div
        style={{
          position: "absolute",
          right: 112,
          top: 156,
          width: 520,
          height: 240,
          borderRadius: 10,
          background: "linear-gradient(135deg, rgba(244,114,182,0.10), rgba(255,255,255,0.10))",
          border: "1px solid rgba(244,114,182,0.12)",
          transform: "perspective(900px) rotateX(58deg) rotateZ(-16deg)",
          boxShadow: "0 42px 90px rgba(236,72,153,0.10)"
        }}
      />
      <div
        style={{
          position: "absolute",
          left: 96,
          bottom: 120,
          width: 420,
          height: 150,
          borderRadius: 10,
          background:
            "linear-gradient(90deg, rgba(236,72,153,0.035) 1px, transparent 1px), linear-gradient(180deg, rgba(31,28,30,0.032) 1px, transparent 1px)",
          backgroundSize: "24px 24px",
          transform: "perspective(800px) rotateX(62deg) rotateZ(12deg)",
          opacity: 0.74
        }}
      />
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
            gap: 18,
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
              minHeight: 468
            }}
          >
            {screenCards[0] ? (
              <EditorialInfoCard card={screenCards[0]} index={0} lead fallbackIcon={fallbackIcon} />
            ) : null}
            <div
              style={{
                display: "grid",
                gridTemplateRows: "1fr 1fr",
                gap: 22,
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
          <div style={{ display: "grid", gap: 16, maxWidth: 1540 }}>
            <AccentBar width={320} />
            <FitTextBlock
              text={detailTitle}
              maxWidth={1500}
              maxFontSize={62}
              minFontSize={34}
              maxLines={2}
              lineHeight={1.08}
              style={{
                fontFamily: editorialFont,
                color: palette.text,
                fontWeight: 720
              }}
            />
            <FitTextBlock
              text={detailSummary}
              maxWidth={1540}
              maxFontSize={34}
              minFontSize={24}
              maxLines={2}
              lineHeight={1.22}
              style={{
                fontFamily: bodyFont,
                color: palette.textSoft,
                fontWeight: 560
              }}
            />
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
