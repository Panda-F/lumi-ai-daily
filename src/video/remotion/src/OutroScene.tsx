import React from "react";
import { AbsoluteFill, Html5Video, Img, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { LUMI_OUTRO_IMAGE_SRC, LUMI_OUTRO_VIDEO_SRC } from "./lumiAssets";
import { palette } from "./theme";
import type { OutroScene as OutroSceneType } from "./types";

const OUTRO_TITLE = "Lumi明天继续陪你看";

export const OutroScene: React.FC<{ scene: OutroSceneType }> = ({ scene }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const settle = spring({
    frame: Math.max(frame - 12, 0),
    fps,
    durationInFrames: 28,
    config: {
      damping: 12,
      stiffness: 120,
      mass: 1
    }
  });

  return (
    <AbsoluteFill
      style={{
        background: `linear-gradient(135deg, ${palette.bg} 0%, ${palette.bgSoft} 58%, ${palette.bgAlt} 100%)`,
        opacity: interpolate(frame, [0, 8, scene.duration_frames - 16, scene.duration_frames], [0, 1, 1, 0], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp"
        })
      }}
    >
      <div
        style={{
          position: "absolute",
          top: 128,
          right: 144,
          width: 320,
          height: 320,
          borderRadius: 999,
          background: "rgba(244,114,182,0.10)"
        }}
      />
      <div
        style={{
          position: "absolute",
          left: 126,
          bottom: 184,
          width: 240,
          height: 240,
          borderRadius: 999,
          background: "rgba(192,132,252,0.10)"
        }}
      />

      <div
        style={{
          position: "absolute",
          inset: "146px 72px 164px",
          display: "grid",
          alignContent: "center",
          justifyItems: "center",
          gap: 28,
          transform: `translateY(${interpolate(settle, [0, 0.6, 1], [22, -8, 0])}px)`
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
            fontFamily: '"Songti SC", "STSong", "Noto Serif SC", serif',
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
            width: 296,
            height: 296,
            borderRadius: 999,
            overflow: "hidden",
            border: "6px solid rgba(255,255,255,0.84)",
            boxShadow: "0 18px 42px rgba(236,72,153,0.12)"
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
            width: 460,
            height: 258,
            borderRadius: 28,
            overflow: "hidden",
            border: "1px solid rgba(244,114,182,0.14)",
            background: "rgba(255,255,255,0.90)",
            boxShadow: "0 18px 42px rgba(236,72,153,0.10)"
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
    </AbsoluteFill>
  );
};
