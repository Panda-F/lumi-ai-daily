import { jsx as _jsx } from "react/jsx-runtime";
import { Composition } from "remotion";
import { DailyReport } from "./DailyReport";
import { DESIGN_HEIGHT, DESIGN_WIDTH } from "./layout";
export const RemotionRoot = () => {
    return (_jsx(Composition, { id: "DailyReport", component: DailyReport, defaultProps: { manifest: null }, durationInFrames: 60, fps: 60, width: DESIGN_WIDTH, height: DESIGN_HEIGHT, calculateMetadata: ({ props }) => {
            const manifest = props.manifest;
            return {
                durationInFrames: manifest.meta.total_frames,
                fps: manifest.meta.fps,
                width: manifest.meta.width,
                height: manifest.meta.height
            };
        } }));
};
