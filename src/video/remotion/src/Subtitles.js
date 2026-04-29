import { jsx as _jsx } from "react/jsx-runtime";
import { useCurrentFrame } from "remotion";
import { fonts } from "./theme";
export const Subtitles = ({ cues, layoutWidth, layoutHeight }) => {
    const frame = useCurrentFrame();
    const activeCue = cues.find((cue) => frame >= cue.start_frame && frame < cue.end_frame) ?? null;
    if (!activeCue || !activeCue.text.trim()) {
        return null;
    }
    const cueDuration = Math.max(1, activeCue.end_frame - activeCue.start_frame);
    const fadeSpan = Math.max(1, Math.min(6, Math.floor(cueDuration / 2)));
    const fadeIn = Math.max(0, Math.min(1, (frame - activeCue.start_frame) / fadeSpan));
    const fadeOut = Math.max(0, Math.min(1, (activeCue.end_frame - frame) / fadeSpan));
    const opacity = Math.min(fadeIn, fadeOut);
    const translateY = 12 * (1 - fadeIn);
    return (_jsx("div", { style: {
            position: "absolute",
            left: 0,
            right: 0,
            bottom: 116,
            display: "flex",
            justifyContent: "center",
            pointerEvents: "none",
            opacity,
            transform: `translateY(${translateY}px)`
        }, children: _jsx("div", { style: {
                maxWidth: Math.min(layoutWidth - 220, 1100),
                minWidth: 280,
                padding: "10px 24px",
                borderRadius: 8,
                background: "rgba(40, 42, 46, 0.86)",
                boxShadow: "0 10px 24px rgba(28, 28, 30, 0.18)",
                color: "#FFFFFF",
                textAlign: "center",
                fontFamily: fonts.body,
                fontSize: 24,
                lineHeight: 1.42,
                fontWeight: 600,
                letterSpacing: 0,
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
                overflow: "hidden"
            }, children: activeCue.text }) }));
};
