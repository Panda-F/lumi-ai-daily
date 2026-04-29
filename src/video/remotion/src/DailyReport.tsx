import React from "react";
import { AbsoluteFill, Audio, interpolate, Sequence, staticFile, useCurrentFrame } from "remotion";
import { Background } from "./Background";
import { FooterRail } from "./FooterRail";
import { inferCategory } from "./helpers";
import { Header } from "./Header";
import { IntroScene } from "./IntroScene";
import { ItemScene } from "./ItemScene";
import { DESIGN_HEIGHT, DESIGN_WIDTH } from "./layout";
import { OutroScene } from "./OutroScene";
import type { ItemScene as ItemSceneType, RemotionManifest } from "./types";

const toStaticFile = (src?: string | null) => (src ? staticFile(src) : null);

export const DailyReport: React.FC<{ manifest: RemotionManifest }> = ({ manifest }) => {
  const outroTitle = "Lumi明天继续陪你看";
  const frame = useCurrentFrame();
  const activeScene = manifest.scenes.find((scene) => frame >= scene.start_frame && frame < scene.end_frame) ?? null;
  const activeSubtitleCues = activeScene ? activeScene.subtitle_cues : [];
  const activeSubtitleText =
    activeSubtitleCues.find((cue) => frame >= cue.start_frame && frame < cue.end_frame)?.text ?? "";
  const bgmSrc = toStaticFile(manifest.meta.bgm_src ?? null);
  const bgmVolume = manifest.meta.bgm_volume ?? 0.18;
  const bgmStartFrame = manifest.meta.bgm_start_frame ?? 0;
  const bgmEndFrame = manifest.meta.bgm_end_frame ?? undefined;
  const outroBgmEnabled = manifest.meta.outro_bgm_enabled ?? false;
  const transitionSfxSrc = toStaticFile(manifest.meta.transition_sfx_src ?? null);
  const transitionSfxVolume = manifest.meta.transition_sfx_volume ?? 0.22;
  const transitionMarkers = manifest.meta.transition_markers ?? [];
  const stageScale = Math.min(
    manifest.meta.width / manifest.meta.design_width,
    manifest.meta.height / manifest.meta.design_height
  );
  const stageLeft = (manifest.meta.width - DESIGN_WIDTH * stageScale) / 2;
  const stageTop = (manifest.meta.height - DESIGN_HEIGHT * stageScale) / 2;
  const introPhase =
    activeScene?.kind === "intro" &&
    frame < activeScene.start_frame + ((activeScene.shot_regions.find((shot) => shot.kind === "intro_title")?.end_frame ?? activeScene.duration_frames * 0.32))
      ? "cover"
      : activeScene?.kind === "intro"
        ? "opening"
        : null;
  const headerSceneKind: "cover" | "opening" | "item" | "outro" =
    introPhase ?? (activeScene?.kind === "item" || activeScene?.kind === "outro" ? activeScene.kind : "cover");
  const activeIndex = activeScene?.kind === "item" ? activeScene.current_index : 0;
  const activeCategory =
    activeScene?.kind === "intro"
      ? "早安"
      : activeScene?.kind === "item"
        ? inferCategory(activeScene.title, activeScene.item_kind)
        : "结尾";
  const tickerTitle =
    activeScene?.kind === "intro"
      ? `今天帮你看了一圈，挑出最值得花时间的 ${manifest.meta.item_count} 条。`
      : activeScene?.kind === "item"
        ? activeScene.display_title
        : activeScene?.kind === "outro"
          ? outroTitle
          : "";
  const smoothstep = (value: number) => value * value * (3 - 2 * value);
  const FADE_FRAMES = 132;
  const introScene = manifest.scenes.find((s) => s.kind === "intro");
  const outroScene = manifest.scenes.find((s) => s.kind === "outro");
  const introEnd = introScene ? introScene.start_frame + introScene.duration_frames : 0;
  const outroStart = outroScene ? outroScene.start_frame : manifest.meta.total_frames;
  const outroEnd = outroScene ? outroScene.end_frame : manifest.meta.total_frames;
  const introWindow = introScene ? Math.max(42, Math.min(FADE_FRAMES, Math.floor(introScene.duration_frames * 0.42))) : 0;
  const outroWindow = outroScene ? Math.max(42, Math.min(FADE_FRAMES, Math.floor(outroScene.duration_frames * 0.55))) : 0;

  const introFadeIn = introScene
    ? smoothstep(
        interpolate(frame, [introScene.start_frame, introScene.start_frame + introWindow], [0, 1], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp"
        })
      )
    : 0;
  const introFadeOut = introScene
    ? smoothstep(
        interpolate(frame, [introEnd - introWindow, introEnd], [1, 0], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp"
        })
      )
    : 0;
  const outroFadeIn = outroScene
    ? smoothstep(
        interpolate(frame, [outroStart, outroStart + outroWindow], [0, 1], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp"
        })
      )
    : 0;
  const outroFadeOut = outroScene
    ? smoothstep(
        interpolate(frame, [outroEnd - outroWindow, outroEnd], [1, 0], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp"
        })
      )
    : 0;
  const introBgmFade = Math.min(introFadeIn, introFadeOut);
  const outroBgmFade = Math.min(outroFadeIn, outroFadeOut);
  const bgmFade =
    introScene && frame < introEnd ? introBgmFade : outroBgmEnabled && outroScene && frame >= outroStart ? outroBgmFade : 1;

  const voiceActive =
    activeScene &&
    typeof activeScene.audio_duration_frames === "number" &&
    frame >= activeScene.start_frame + (activeScene.audio_offset_frames ?? 0) &&
    frame < activeScene.start_frame + (activeScene.audio_offset_frames ?? 0) + activeScene.audio_duration_frames + 6;
  const effectiveBgmVolume = bgmFade * (voiceActive ? bgmVolume * 0.44 : bgmVolume);
  const effectiveTransitionSfxVolume = Math.min(transitionSfxVolume, 0.11);
  const itemLabels =
    manifest.meta.item_labels && manifest.meta.item_labels.length
      ? manifest.meta.item_labels
      : manifest.report.items.map((item) => item.item_label || item.title);

  return (
    <AbsoluteFill style={{ backgroundColor: "#FFF8F5" }}>
      <Background />
      <div
        style={{
          position: "absolute",
          left: stageLeft,
          top: stageTop,
          width: DESIGN_WIDTH,
          height: DESIGN_HEIGHT,
          transform: `scale(${stageScale})`,
          transformOrigin: "top left",
          overflow: "hidden"
        }}
      >
        {bgmSrc ? (
          <Audio src={bgmSrc} volume={effectiveBgmVolume} startFrom={bgmStartFrame} endAt={bgmEndFrame} />
        ) : null}
        {transitionSfxSrc
          ? transitionMarkers.map((marker) => (
              <Sequence key={`transition-sfx-${marker.scene_id}-${marker.frame}`} from={marker.frame}>
                <Audio src={transitionSfxSrc} volume={effectiveTransitionSfxVolume} />
              </Sequence>
            ))
          : null}

        {manifest.scenes.map((scene) => {
          const audioSrc = toStaticFile(scene.audio_src ?? null);
          return (
            <Sequence key={scene.id} from={scene.start_frame} durationInFrames={scene.duration_frames}>
              {scene.kind === "intro" ? (
                <IntroScene
                  scene={scene}
                  lumiAvatarSrc={manifest.meta.lumi_avatar_src ?? null}
                  issueQuoteText={manifest.meta.issue_quote_text ?? undefined}
                  issueQuoteAuthor={manifest.meta.issue_quote_author ?? undefined}
                  primaryHook={manifest.meta.primary_hook ?? undefined}
                />
              ) : null}
              {scene.kind === "item" ? (
                <ItemScene
                  scene={scene as ItemSceneType}
                  lumiAvatarSrc={manifest.meta.lumi_avatar_src ?? null}
                  issueQuoteText={manifest.meta.issue_quote_text ?? undefined}
                  issueQuoteAuthor={manifest.meta.issue_quote_author ?? undefined}
                />
              ) : null}
              {scene.kind === "outro" ? <OutroScene scene={scene} /> : null}
              {audioSrc ? (
                <Sequence from={scene.audio_offset_frames ?? 0}>
                  <Audio src={audioSrc} />
                </Sequence>
              ) : null}
            </Sequence>
          );
        })}

        <Header
          dateLabel={manifest.meta.date}
          issueLabel={manifest.meta.issue_label}
          activeCategory={activeCategory}
          activeIndex={activeIndex}
          totalItems={manifest.meta.item_count}
          sceneKind={headerSceneKind}
          itemLabels={itemLabels}
        />

        <FooterRail
          items={manifest.report.items}
          activeIndex={activeIndex}
          currentTitle={tickerTitle}
          subtitleText={activeSubtitleText}
          sceneKind={headerSceneKind}
          issueLabel={manifest.meta.issue_label}
        />
      </div>
    </AbsoluteFill>
  );
};
