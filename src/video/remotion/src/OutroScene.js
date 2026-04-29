import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { fonts, palette } from "./theme";
export const OutroScene = ({ scene }) => {
    const frame = useCurrentFrame();
    const { fps } = useVideoConfig();
    const bow = spring({
        frame: Math.max(frame - 12, 0),
        fps,
        durationInFrames: 28,
        config: {
            damping: 12,
            stiffness: 120,
            mass: 1
        }
    });
    return (_jsx(AbsoluteFill, { style: {
            background: `linear-gradient(135deg, ${palette.bg} 0%, ${palette.bgSoft} 58%, ${palette.bgAlt} 100%)`,
            opacity: interpolate(frame, [0, 8, scene.duration_frames - 16, scene.duration_frames], [0, 1, 1, 0], {
                extrapolateLeft: "clamp",
                extrapolateRight: "clamp"
            })
        }, children: _jsxs("div", { style: {
                position: "absolute",
                inset: "140px 72px 146px",
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                gap: 18,
                transform: `translateY(${interpolate(bow, [0, 0.6, 1], [20, -8, 0])}px)`
            }, children: [_jsx("div", { style: {
                        padding: "6px 18px",
                        borderRadius: 8,
                        background: `linear-gradient(135deg, ${palette.accent} 0%, ${palette.purple} 100%)`,
                        color: palette.white,
                        fontFamily: fonts.body,
                        fontSize: 14,
                        fontWeight: 700,
                        letterSpacing: 1.2
                    }, children: "AI\u901F\u9012" }), _jsx("div", { style: {
                        fontFamily: fonts.display,
                        fontSize: 56,
                        fontWeight: 900,
                        color: palette.text
                    }, children: scene.line_one }), _jsx("div", { style: {
                        fontFamily: fonts.body,
                        fontSize: 22,
                        fontWeight: 600,
                        color: palette.textSoft
                    }, children: scene.line_two }), _jsx("div", { style: {
                        marginTop: 10,
                        fontFamily: fonts.body,
                        fontSize: 15,
                        color: palette.weakText,
                        fontStyle: "italic"
                    }, children: "AI \u5728\u53D8\uFF0C\u5224\u65AD\u5148\u884C\u3002" })] }) }));
};
