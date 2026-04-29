import React from "react";
import { Composition } from "remotion";
import { DailyReport } from "./DailyReport";
import { DESIGN_HEIGHT, DESIGN_WIDTH } from "./layout";
import { StyleDemo } from "./StyleDemo";
import type { RemotionManifest } from "./types";

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="DailyReport"
        component={DailyReport}
        defaultProps={{ manifest: null as unknown as RemotionManifest }}
        durationInFrames={60}
        fps={60}
        width={DESIGN_WIDTH}
        height={DESIGN_HEIGHT}
        calculateMetadata={({ props }) => {
          const manifest = props.manifest as RemotionManifest;
          return {
            durationInFrames: manifest.meta.total_frames,
            fps: manifest.meta.fps,
            width: manifest.meta.width,
            height: manifest.meta.height
          };
        }}
      />
      <Composition
        id="StyleDemo"
        component={StyleDemo}
        defaultProps={{ variant: "cover" as const, openingCount: 6, openingPage: 0 }}
        durationInFrames={120}
        fps={60}
        width={DESIGN_WIDTH}
        height={DESIGN_HEIGHT}
      />
    </>
  );
};
