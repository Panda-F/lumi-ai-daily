import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { AbsoluteFill, Audio, Sequence, staticFile, useCurrentFrame } from "remotion";
import { Background } from "./Background";
import { FooterRail } from "./FooterRail";
import { inferCategory } from "./helpers";
import { Header } from "./Header";
import { IntroScene } from "./IntroScene";
import { ItemScene } from "./ItemScene";
import { DESIGN_HEIGHT, DESIGN_WIDTH } from "./layout";
import { OutroScene } from "./OutroScene";
const toStaticFile = (src) => (src ? staticFile(src) : null);
export const DailyReport = ({ manifest }) => {
    const frame = useCurrentFrame();
    const activeScene = manifest.scenes.find((scene) => frame >= scene.start_frame && frame < scene.end_frame) ?? null;
    const activeSubtitleCues = activeScene ? activeScene.subtitle_cues : [];
    const activeSubtitleText = activeSubtitleCues.find((cue) => frame >= cue.start_frame && frame < cue.end_frame)?.text ?? "";
    const bgmSrc = toStaticFile(manifest.meta.bgm_src ?? null);
    const bgmVolume = manifest.meta.bgm_volume ?? 0.14;
    const transitionSfxSrc = toStaticFile(manifest.meta.transition_sfx_src ?? null);
    const transitionSfxVolume = manifest.meta.transition_sfx_volume ?? 0.22;
    const transitionMarkers = manifest.meta.transition_markers ?? [];
    const stageScale = Math.min(manifest.meta.width / manifest.meta.design_width, manifest.meta.height / manifest.meta.design_height);
    const stageLeft = (manifest.meta.width - DESIGN_WIDTH * stageScale) / 2;
    const stageTop = (manifest.meta.height - DESIGN_HEIGHT * stageScale) / 2;
    const activeIndex = activeScene?.kind === "item" ? activeScene.current_index : 0;
    const activeCategory = activeScene?.kind === "intro"
        ? "早安"
        : activeScene?.kind === "item"
            ? inferCategory(activeScene.title, activeScene.item_kind)
            : "研究追踪";
    const tickerTitle = activeScene?.kind === "intro"
        ? "今天帮你看了一圈，挑出最值得花时间的 6 条。"
        : activeScene?.kind === "item"
            ? activeScene.display_title
            : activeScene?.kind === "outro"
                ? activeScene.line_one
                : "";
    const voiceActive = activeScene &&
        typeof activeScene.audio_duration_frames === "number" &&
        frame >= activeScene.start_frame + (activeScene.audio_offset_frames ?? 0) &&
        frame < activeScene.start_frame + (activeScene.audio_offset_frames ?? 0) + activeScene.audio_duration_frames + 6;
    const effectiveBgmVolume = voiceActive ? bgmVolume * 0.72 : bgmVolume;
    return (_jsxs(AbsoluteFill, { style: { backgroundColor: "#FFF8F5" }, children: [_jsx(Background, {}), _jsxs("div", { style: {
                    position: "absolute",
                    left: stageLeft,
                    top: stageTop,
                    width: DESIGN_WIDTH,
                    height: DESIGN_HEIGHT,
                    transform: `scale(${stageScale})`,
                    transformOrigin: "top left",
                    overflow: "hidden"
                }, children: [bgmSrc ? _jsx(Audio, { src: bgmSrc, volume: effectiveBgmVolume }) : null, transitionSfxSrc
                        ? transitionMarkers.map((marker) => (_jsx(Sequence, { from: marker.frame, children: _jsx(Audio, { src: transitionSfxSrc, volume: transitionSfxVolume }) }, `transition-sfx-${marker.scene_id}-${marker.frame}`)))
                        : null, _jsx(Header, { dateLabel: manifest.meta.date, issueLabel: manifest.meta.issue_label, activeCategory: activeCategory, activeIndex: activeIndex, totalItems: manifest.meta.item_count }), manifest.scenes.map((scene) => {
                        const audioSrc = toStaticFile(scene.audio_src ?? null);
                        return (_jsxs(Sequence, { from: scene.start_frame, durationInFrames: scene.duration_frames, children: [scene.kind === "intro" ? (_jsx(IntroScene, { scene: scene, lumiAvatarSrc: manifest.meta.lumi_avatar_src ?? null })) : null, scene.kind === "item" ? (_jsx(ItemScene, { scene: scene, lumiAvatarSrc: manifest.meta.lumi_avatar_src ?? null })) : null, scene.kind === "outro" ? _jsx(OutroScene, { scene: scene }) : null, audioSrc ? (_jsx(Sequence, { from: scene.audio_offset_frames ?? 0, children: _jsx(Audio, { src: audioSrc }) })) : null] }, scene.id));
                    }), _jsx(FooterRail, { items: manifest.report.items, activeIndex: activeIndex, currentTitle: tickerTitle, subtitleText: activeSubtitleText, sceneKind: activeScene?.kind ?? "intro", issueLabel: manifest.meta.issue_label })] })] }));
};
