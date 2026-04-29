import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { Icon } from "./icons";
import { renderMedia } from "./helpers";
import { fonts, palette } from "./theme";
const formatFriendlyDate = (dateLabel) => {
    const match = dateLabel.match(/(\d{4})\.(\d{1,2})\.(\d{1,2})/);
    if (!match) {
        return dateLabel;
    }
    return `${Number(match[2])}月${Number(match[3])}日`;
};
const Particle = ({ x, y, size, color, frame, delay }) => {
    const lift = Math.sin((frame + delay) / 18) * 10;
    return (_jsx("div", { style: {
            position: "absolute",
            left: x,
            top: y + lift,
            width: size,
            height: size,
            borderRadius: 999,
            background: color,
            opacity: 0.95
        } }));
};
export const IntroScene = ({ scene }) => {
    const frame = useCurrentFrame();
    const { fps } = useVideoConfig();
    const leftSpring = spring({
        frame,
        fps,
        config: { damping: 16, stiffness: 96, mass: 0.94 }
    });
    const rightSpring = spring({
        frame: Math.max(frame - 8, 0),
        fps,
        config: { damping: 18, stiffness: 104, mass: 0.9 }
    });
    const summarySpring = spring({
        frame: Math.max(frame - 16, 0),
        fps,
        config: { damping: 17, stiffness: 112, mass: 0.92 }
    });
    const pulse = 1 + Math.sin(frame / 18) * 0.018;
    const mediaSrc = scene.lumi_intro_src || scene.lead_media_src;
    const scanTop = ((frame * 3.2) % 760) - 20;
    return (_jsx(AbsoluteFill, { style: { overflow: "hidden" }, children: _jsxs("div", { style: {
                position: "absolute",
                inset: "98px 0 44px",
                display: "flex"
            }, children: [_jsxs("div", { style: {
                        width: "46%",
                        position: "relative",
                        paddingTop: 100,
                        display: "flex",
                        flexDirection: "column",
                        alignItems: "center",
                        justifyContent: "flex-start",
                        overflow: "hidden"
                    }, children: [_jsx("div", { style: {
                                position: "absolute",
                                left: 0,
                                right: 0,
                                top: scanTop,
                                height: 2,
                                background: "linear-gradient(to right, transparent, rgba(244,114,182,0.5), transparent)"
                            } }), _jsx(Particle, { x: 60, y: 120, size: 6, color: "#F9A8D4", frame: frame, delay: 0 }), _jsx(Particle, { x: 140, y: 230, size: 4, color: "#C084FC", frame: frame, delay: 8 }), _jsx(Particle, { x: 86, y: 460, size: 5, color: "#FCA5A5", frame: frame, delay: 15 }), _jsx(Particle, { x: 122, y: 690, size: 3, color: "#F472B6", frame: frame, delay: 5 }), _jsx(Particle, { x: 730, y: 180, size: 5, color: "#C084FC", frame: frame, delay: 11 }), _jsx(Particle, { x: 780, y: 380, size: 4, color: "#F9A8D4", frame: frame, delay: 21 }), _jsx(Particle, { x: 720, y: 610, size: 6, color: "#F472B6", frame: frame, delay: 3 }), _jsx(Particle, { x: 190, y: 856, size: 3, color: "#FCA5A5", frame: frame, delay: 17 }), _jsxs("div", { style: {
                                position: "relative",
                                width: 460,
                                height: 460,
                                transform: `translateY(${interpolate(leftSpring, [0, 1], [36, 0])}px) scale(${pulse})`,
                                opacity: interpolate(leftSpring, [0, 1], [0, 1])
                            }, children: [_jsx("div", { style: {
                                        position: "absolute",
                                        inset: 0,
                                        borderRadius: 999,
                                        border: "1.5px dashed rgba(244,114,182,0.35)"
                                    } }), _jsx("div", { style: {
                                        position: "absolute",
                                        inset: 20,
                                        borderRadius: 999,
                                        boxShadow: "0 0 0 6px rgba(244,114,182,0.18), 0 18px 48px rgba(244,114,182,0.16)"
                                    } }), _jsx("div", { style: {
                                        position: "absolute",
                                        inset: 20,
                                        borderRadius: 999,
                                        overflow: "hidden",
                                        background: "linear-gradient(135deg, #FED7E2 0%, #E9D5FF 100%)",
                                        border: "1px solid rgba(244,114,182,0.24)"
                                    }, children: renderMedia(mediaSrc, scene.primary_media_kind || "image", "cover") })] }), _jsxs("div", { style: {
                                marginTop: 24,
                                padding: "8px 22px",
                                borderRadius: 999,
                                background: `linear-gradient(135deg, ${palette.accent} 0%, ${palette.purple} 100%)`,
                                color: palette.white,
                                display: "inline-flex",
                                alignItems: "center",
                                gap: 8,
                                fontFamily: fonts.body,
                                fontSize: 15,
                                fontStyle: "italic",
                                fontWeight: 700,
                                boxShadow: "0 4px 16px rgba(244,114,182,0.35)"
                            }, children: [_jsx(Icon, { name: "sparkles", size: 14, color: "#FFFFFF", strokeWidth: 2.1 }), "Lumi \u65E9\u5B89\u64AD\u62A5"] })] }), _jsxs("div", { style: {
                        width: "54%",
                        position: "relative",
                        padding: "110px 88px 0 64px",
                        overflow: "hidden"
                    }, children: [_jsxs("div", { style: {
                                position: "absolute",
                                top: 36,
                                right: 88,
                                display: "flex",
                                alignItems: "center",
                                gap: 12,
                                transform: `translateY(${interpolate(rightSpring, [0, 1], [28, 0])}px)`,
                                opacity: interpolate(rightSpring, [0, 1], [0, 1])
                            }, children: [_jsx("div", { style: {
                                        background: `linear-gradient(135deg, ${palette.accent} 0%, ${palette.purple} 100%)`,
                                        color: palette.white,
                                        fontSize: 13,
                                        fontWeight: 700,
                                        borderRadius: 999,
                                        padding: "5px 16px",
                                        boxShadow: "0 2px 10px rgba(244,114,182,0.30)"
                                    }, children: "AI\u901F\u9012" }), _jsxs("div", { style: { fontFamily: fonts.body, fontSize: 13, color: palette.muted }, children: [scene.date_label, " ", scene.issue_label] })] }), _jsx("div", { style: {
                                position: "absolute",
                                bottom: -20,
                                right: -10,
                                fontFamily: fonts.display,
                                fontSize: 380,
                                fontWeight: 900,
                                lineHeight: 1,
                                color: "rgba(244,114,182,0.05)",
                                userSelect: "none"
                            }, children: scene.issue_label.replace(/[^\d]/g, "") || "24" }), _jsxs("div", { style: {
                                position: "relative",
                                zIndex: 2,
                                transform: `translateY(${interpolate(rightSpring, [0, 1], [28, 0])}px)`,
                                opacity: interpolate(rightSpring, [0, 1], [0, 1])
                            }, children: [_jsx("div", { style: {
                                        fontFamily: fonts.body,
                                        fontSize: 11,
                                        fontWeight: 600,
                                        letterSpacing: 5,
                                        textTransform: "uppercase",
                                        color: palette.accent
                                    }, children: "DAILY BRIEFING \u00B7 \u65E9\u5B89" }), _jsxs("div", { style: {
                                        marginTop: 14,
                                        display: "flex",
                                        alignItems: "center",
                                        gap: 18,
                                        fontFamily: fonts.display,
                                        fontSize: 88,
                                        lineHeight: 1.05,
                                        fontWeight: 900,
                                        color: palette.text
                                    }, children: [_jsx("span", { children: "\u65E9\u4E0A\u597D" }), _jsx(Icon, { name: "sun", size: 80, color: palette.accent, strokeWidth: 1.5 })] }), _jsxs("div", { style: {
                                        marginTop: 10,
                                        fontFamily: fonts.body,
                                        fontSize: 20,
                                        lineHeight: 1.5,
                                        color: palette.textSoft
                                    }, children: ["\u4ECA\u5929\u662F ", _jsx("strong", { children: formatFriendlyDate(scene.date_label) }), "\uFF0CAI\u901F\u9012 ", scene.issue_label, "\uFF0C\u5E2E\u4F60\u538B\u6210", " ", scene.headlines.length, " \u6761\u91CD\u70B9"] }), _jsx("div", { style: {
                                        width: 108,
                                        height: 3,
                                        borderRadius: 999,
                                        marginTop: 22,
                                        background: `linear-gradient(90deg, ${palette.accent} 0%, ${palette.purple} 100%)`
                                    } }), _jsx("div", { style: { marginTop: 24, display: "flex", gap: 10, flexWrap: "wrap" }, children: scene.trend_words.map((word) => (_jsx("div", { style: {
                                            border: "1.5px solid rgba(244,114,182,0.50)",
                                            color: palette.deep,
                                            background: "rgba(244,114,182,0.08)",
                                            borderRadius: 8,
                                            padding: "6px 16px",
                                            fontSize: 13,
                                            fontWeight: 600
                                        }, children: word }, word))) }), _jsxs("div", { style: {
                                        marginTop: 26,
                                        display: "grid",
                                        gap: 16,
                                        transform: `translateY(${interpolate(summarySpring, [0, 1], [18, 0])}px)`,
                                        opacity: interpolate(summarySpring, [0, 1], [0, 1])
                                    }, children: [_jsxs("div", { style: {
                                                borderRadius: 12,
                                                background: "rgba(255,255,255,0.94)",
                                                border: `1px solid ${palette.cardBorder}`,
                                                boxShadow: `0 12px 32px ${palette.shadow}`,
                                                padding: "22px 24px"
                                            }, children: [_jsx("div", { style: {
                                                        fontFamily: fonts.body,
                                                        fontSize: 12,
                                                        letterSpacing: 2,
                                                        textTransform: "uppercase",
                                                        color: palette.weakText,
                                                        fontWeight: 700
                                                    }, children: "\u4ECA\u5929\u5148\u770B\u8FD9\u51E0\u6761" }), _jsx("div", { style: { marginTop: 16, display: "grid", gap: 12 }, children: scene.agenda_lines.slice(0, 3).map((line, index) => (_jsxs("div", { style: {
                                                            display: "grid",
                                                            gridTemplateColumns: "46px minmax(0, 1fr)",
                                                            gap: 14,
                                                            alignItems: "start"
                                                        }, children: [_jsx("div", { style: {
                                                                    color: palette.deep,
                                                                    fontFamily: fonts.display,
                                                                    fontSize: 30,
                                                                    lineHeight: 1,
                                                                    fontWeight: 900
                                                                }, children: String(index + 1).padStart(2, "0") }), _jsx("div", { style: {
                                                                    fontFamily: fonts.body,
                                                                    fontSize: 27,
                                                                    lineHeight: 1.42,
                                                                    color: palette.text
                                                                }, children: line })] }, `${line}-${index}`))) })] }), _jsxs("div", { style: {
                                                borderRadius: 12,
                                                border: `1px solid ${palette.chromeBorder}`,
                                                background: "rgba(255,255,255,0.54)",
                                                padding: "18px 22px"
                                            }, children: [_jsx("div", { style: {
                                                        fontFamily: fonts.body,
                                                        fontSize: 15,
                                                        lineHeight: 1.8,
                                                        color: palette.muted
                                                    }, children: scene.opening }), _jsx("div", { style: {
                                                        marginTop: 12,
                                                        fontFamily: fonts.body,
                                                        fontSize: 16,
                                                        lineHeight: 1.85,
                                                        color: palette.textSoft
                                                    }, children: scene.transition })] }), _jsx("div", { style: {
                                                fontFamily: fonts.body,
                                                fontSize: 15,
                                                color: palette.weakText,
                                                fontStyle: "italic"
                                            }, children: "AI \u5728\u53D8\uFF0C\u5224\u65AD\u5148\u884C\u3002" })] })] })] })] }) }));
};
