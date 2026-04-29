import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { AbsoluteFill, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { Icon } from "./icons";
import { inferIcon, renderMedia } from "./helpers";
import { fonts, palette } from "./theme";
const QuoteBlock = ({ text, frame, compact = false }) => {
    const breath = 0.22 + ((Math.sin(frame / 18) + 1) / 2) * 0.18;
    return (_jsxs("div", { style: {
            background: "linear-gradient(135deg, #FDF2F8 0%, #F5F0FF 100%)",
            border: `1.5px solid rgba(244,114,182,${breath.toFixed(2)})`,
            borderRadius: 16,
            padding: compact ? "28px 32px" : "36px 40px",
            position: "relative",
            overflow: "hidden",
            boxShadow: "0 4px 32px rgba(244,114,182,0.10)",
            minHeight: compact ? 220 : 320,
            display: "flex",
            flexDirection: "column",
            justifyContent: "center"
        }, children: [_jsx("div", { style: {
                    position: "absolute",
                    top: 12,
                    left: 24,
                    fontSize: 100,
                    fontFamily: "Georgia, serif",
                    lineHeight: 1,
                    color: "rgba(244,114,182,0.18)"
                }, children: "\"" }), _jsx("div", { style: {
                    position: "relative",
                    zIndex: 1,
                    paddingTop: 24,
                    fontFamily: fonts.body,
                    fontSize: compact ? 28 : 32,
                    lineHeight: 1.5,
                    fontWeight: 700,
                    fontStyle: "italic",
                    color: palette.deep
                }, children: text })] }));
};
const MediaPanel = ({ src, kind }) => {
    if (!src) {
        return null;
    }
    return (_jsxs("div", { style: {
            height: 278,
            borderRadius: 12,
            border: `1px solid ${palette.cardBorder}`,
            background: "rgba(255,255,255,0.94)",
            boxShadow: `0 14px 30px ${palette.shadow}`,
            overflow: "hidden",
            position: "relative"
        }, children: [_jsx("div", { style: {
                    position: "absolute",
                    inset: 18,
                    borderRadius: 8,
                    overflow: "hidden",
                    background: "rgba(255,255,255,0.80)"
                }, children: renderMedia(src, kind ?? null, "contain") }), kind === "gif" || kind === "video" ? (_jsx("div", { style: {
                    position: "absolute",
                    top: 14,
                    right: 14,
                    padding: "5px 10px",
                    borderRadius: 8,
                    background: "rgba(28,28,30,0.72)",
                    color: palette.white,
                    fontFamily: fonts.body,
                    fontSize: 11,
                    fontWeight: 700,
                    letterSpacing: 1
                }, children: "\u52A8\u56FE" })) : null] }));
};
export const ItemScene = ({ scene, lumiAvatarSrc }) => {
    const frame = useCurrentFrame();
    const { fps } = useVideoConfig();
    const titleSpring = spring({
        frame: Math.max(frame - 2, 0),
        fps,
        config: { damping: 16, stiffness: 128, mass: 0.92 }
    });
    const cardSpring = spring({
        frame: Math.max(frame - 10, 0),
        fps,
        config: { damping: 18, stiffness: 132, mass: 0.92 }
    });
    const mediaSpring = spring({
        frame: Math.max(frame - 14, 0),
        fps,
        config: { damping: 18, stiffness: 120, mass: 0.92 }
    });
    const sceneOpacity = interpolate(frame, [0, 8, scene.duration_frames - 16, scene.duration_frames], [0, 1, 1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
    const iconName = inferIcon(scene.display_title || scene.title, scene.item_kind);
    const avatarSrc = lumiAvatarSrc ? staticFile(lumiAvatarSrc) : null;
    const showMedia = Boolean(scene.primary_media_src);
    const quoteText = scene.quote || scene.takeaway || scene.display_title || scene.title;
    const quoteDominant = scene.template_variant === "quote_dominant" || scene.template_variant === "research_quote_fallback";
    const factDominant = scene.template_variant === "fact_dominant_fallback";
    return (_jsx(AbsoluteFill, { style: { opacity: sceneOpacity, overflow: "hidden" }, children: _jsxs("div", { style: {
                position: "absolute",
                inset: "100px 0 96px",
                display: "flex"
            }, children: [_jsxs("div", { style: {
                        width: "46%",
                        padding: "0 52px 60px 72px",
                        position: "relative",
                        overflow: "hidden"
                    }, children: [_jsx("div", { style: {
                                position: "absolute",
                                top: 0,
                                left: 0,
                                width: 500,
                                height: 500,
                                borderRadius: 999,
                                background: "radial-gradient(ellipse at 0% 0%, rgba(244,114,182,0.08) 0%, transparent 60%)"
                            } }), _jsxs("div", { style: {
                                position: "relative",
                                zIndex: 2,
                                transform: `translateY(${interpolate(titleSpring, [0, 1], [28, 0])}px)`,
                                opacity: interpolate(titleSpring, [0, 1], [0, 1])
                            }, children: [_jsx("div", { style: { display: "inline-flex", marginBottom: 18 }, children: _jsx(Icon, { name: iconName, size: 44, color: palette.deep, strokeWidth: 1.5 }) }), _jsx("div", { style: {
                                        fontFamily: fonts.display,
                                        fontSize: 46,
                                        lineHeight: 1.22,
                                        fontWeight: 900,
                                        color: palette.text,
                                        maxWidth: 760
                                    }, children: scene.display_title }), _jsx("div", { style: {
                                        width: interpolate(titleSpring, [0, 1], [0, 72]),
                                        height: 3,
                                        borderRadius: 999,
                                        marginTop: 12,
                                        background: `linear-gradient(90deg, ${palette.accent} 0%, ${palette.purple} 100%)`
                                    } }), _jsxs("div", { style: {
                                        marginTop: 22,
                                        border: `1px solid rgba(244,114,182,0.22)`,
                                        borderRadius: 12,
                                        padding: "18px 20px",
                                        background: "transparent",
                                        opacity: interpolate(cardSpring, [0, 1], [0, 1]),
                                        transform: `translateY(${interpolate(cardSpring, [0, 1], [20, 0])}px)`
                                    }, children: [_jsx("div", { style: {
                                                fontSize: 10,
                                                letterSpacing: 2,
                                                textTransform: "uppercase",
                                                color: palette.weakText,
                                                marginBottom: 10,
                                                fontWeight: 600
                                            }, children: "\u53D1\u751F\u4E86\u4EC0\u4E48" }), _jsx("div", { style: { display: "grid", gap: 14 }, children: scene.fact_points.map((point, index) => (_jsxs("div", { style: {
                                                    display: "grid",
                                                    gridTemplateColumns: "28px minmax(0, 1fr)",
                                                    gap: 10,
                                                    alignItems: "start"
                                                }, children: [_jsx("div", { style: {
                                                            width: 24,
                                                            height: 24,
                                                            borderRadius: 8,
                                                            background: "rgba(244,114,182,0.12)",
                                                            color: palette.deep,
                                                            display: "flex",
                                                            alignItems: "center",
                                                            justifyContent: "center",
                                                            fontSize: 12,
                                                            fontWeight: 800
                                                        }, children: index + 1 }), _jsx("div", { style: {
                                                            fontFamily: fonts.body,
                                                            fontSize: 15,
                                                            lineHeight: 1.7,
                                                            color: palette.textSoft
                                                        }, children: point })] }, `${point}-${index}`))) })] }), _jsxs("div", { style: {
                                        marginTop: 14,
                                        background: palette.white,
                                        border: `1px solid rgba(244,114,182,0.18)`,
                                        borderRadius: 12,
                                        padding: "18px 20px",
                                        boxShadow: "0 2px 20px rgba(244,114,182,0.10)",
                                        opacity: interpolate(cardSpring, [0, 1], [0, 1]),
                                        transform: `translateY(${interpolate(cardSpring, [0, 1], [14, 0])}px)`
                                    }, children: [_jsxs("div", { style: {
                                                display: "inline-flex",
                                                alignItems: "center",
                                                gap: 6,
                                                background: `linear-gradient(135deg, ${palette.accent} 0%, ${palette.purple} 100%)`,
                                                color: palette.white,
                                                fontSize: 10,
                                                fontWeight: 700,
                                                borderRadius: 999,
                                                padding: "4px 12px",
                                                letterSpacing: 1.5,
                                                textTransform: "uppercase"
                                            }, children: [_jsx(Icon, { name: "sparkles", size: 12, color: "#FFFFFF", strokeWidth: 2.2 }), "\u503C\u5F97\u770B\uFF0C\u56E0\u4E3A"] }), _jsx("div", { style: {
                                                marginTop: 14,
                                                fontFamily: fonts.body,
                                                fontSize: 17,
                                                lineHeight: 1.8,
                                                color: palette.textSoft,
                                                borderLeft: `3px solid ${palette.accent}`,
                                                paddingLeft: 16
                                            }, children: scene.takeaway })] })] })] }), _jsx("div", { style: {
                        width: 1,
                        margin: "40px 0",
                        background: "linear-gradient(to bottom, transparent, rgba(244,114,182,0.30) 30%, rgba(244,114,182,0.30) 70%, transparent)"
                    } }), _jsxs("div", { style: {
                        width: "54%",
                        padding: "0 80px 60px 40px",
                        transform: `translateY(${interpolate(mediaSpring, [0, 1], [24, 0])}px)`,
                        opacity: interpolate(mediaSpring, [0, 1], [0, 1])
                    }, children: [_jsxs("div", { style: {
                                fontSize: 12,
                                color: palette.weakText,
                                marginBottom: 20,
                                letterSpacing: 0.5,
                                display: "inline-flex",
                                alignItems: "center",
                                gap: 6
                            }, children: [_jsx(Icon, { name: "link-2", size: 12, color: palette.weakText, strokeWidth: 2.2 }), scene.source_domain || "source"] }), _jsxs("div", { style: {
                                display: "flex",
                                flexDirection: "column",
                                gap: showMedia ? 18 : 24,
                                minHeight: 620
                            }, children: [showMedia ? _jsx(MediaPanel, { src: scene.primary_media_src, kind: scene.primary_media_kind }) : null, _jsx("div", { style: { flex: quoteDominant || factDominant ? 1 : "unset" }, children: _jsx(QuoteBlock, { text: quoteText, frame: frame, compact: showMedia }) }), _jsxs("div", { style: { display: "flex", alignItems: "center", gap: 12, marginTop: quoteDominant ? "auto" : 0 }, children: [_jsx("div", { style: {
                                                width: 52,
                                                height: 52,
                                                borderRadius: 999,
                                                overflow: "hidden",
                                                border: "2px solid rgba(244,114,182,0.40)",
                                                boxShadow: "0 0 12px rgba(244,114,182,0.20)",
                                                background: "linear-gradient(135deg,#FECDD3,#E9D5FF)",
                                                flexShrink: 0
                                            }, children: avatarSrc ? (_jsx("img", { src: avatarSrc, style: { width: "100%", height: "100%", objectFit: "cover", objectPosition: "center top" } })) : null }), _jsxs("div", { style: { display: "flex", flexDirection: "column", gap: 2 }, children: [_jsx("div", { style: { fontSize: 13, fontWeight: 700, color: palette.text }, children: "Lumi" }), _jsx("div", { style: { fontSize: 11, color: palette.weakText, letterSpacing: 0.5 }, children: "\u6BCF\u5929\u66FF\u4F60\u770B\u5B8C\uFF0C\u6311\u51FA\u6700\u91CD\u8981\u7684" })] })] })] })] })] }) }));
};
