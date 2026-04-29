import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { AbsoluteFill } from "remotion";
import { shortenLabel, stripLeadDecor } from "./helpers";
import { fonts, palette } from "./theme";
export const FooterRail = ({ items, activeIndex, currentTitle, subtitleText, sceneKind, issueLabel }) => {
    if (sceneKind === "intro") {
        return (_jsx(AbsoluteFill, { style: { pointerEvents: "none", justifyContent: "flex-end" }, children: _jsxs("div", { style: {
                    height: 44,
                    background: "rgba(255,255,255,0.70)",
                    borderTop: "1px solid rgba(244,114,182,0.20)",
                    backdropFilter: "blur(12px)",
                    display: "flex",
                    alignItems: "center",
                    padding: "0 52px",
                    position: "relative"
                }, children: [_jsx("div", { style: {
                            width: 7,
                            height: 7,
                            borderRadius: 999,
                            background: palette.accent,
                            marginRight: 8,
                            boxShadow: "0 0 6px rgba(244,114,182,0.60)"
                        } }), _jsx("div", { style: {
                            fontSize: 12,
                            color: palette.deep,
                            fontWeight: 700,
                            letterSpacing: 1,
                            marginRight: "auto"
                        }, children: "LIVE" }), _jsx("div", { style: {
                            position: "absolute",
                            left: "50%",
                            transform: "translateX(-50%)",
                            fontSize: 12,
                            color: palette.textSoft,
                            letterSpacing: 1,
                            maxWidth: 860,
                            whiteSpace: "normal",
                            overflow: "hidden"
                        }, children: subtitleText || "今天帮你看了一圈，挑出最值得花时间的 6 条。" }), _jsx("div", { style: {
                            marginLeft: "auto",
                            fontSize: 12,
                            color: palette.weakText,
                            letterSpacing: 0.5
                        }, children: issueLabel })] }) }));
    }
    const lowerText = stripLeadDecor(subtitleText || currentTitle);
    return (_jsxs(AbsoluteFill, { style: {
            pointerEvents: "none",
            justifyContent: "flex-end"
        }, children: [_jsx("div", { style: {
                    height: 44,
                    display: "grid",
                    gridTemplateColumns: `repeat(${Math.max(1, items.length)}, minmax(0, 1fr))`,
                    gap: 0,
                    background: "rgba(255,255,255,0.76)",
                    borderTop: "1px solid rgba(244,114,182,0.16)",
                    backdropFilter: "blur(10px)"
                }, children: items.map((item, index) => {
                    const active = index + 1 === activeIndex;
                    return (_jsx("div", { style: {
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                            padding: "0 10px",
                            borderRight: index < items.length - 1 ? "1px solid rgba(244,114,182,0.10)" : "none",
                            background: active ? "rgba(244,114,182,0.12)" : "transparent",
                            color: active ? palette.deep : palette.muted,
                            fontFamily: fonts.body,
                            fontSize: 11,
                            fontWeight: active ? 700 : 500,
                            textAlign: "center",
                            lineHeight: 1.15
                        }, children: shortenLabel(item.title, 14) }, `${item.title}-${index}`));
                }) }), _jsxs("div", { style: {
                    height: 52,
                    background: palette.subtitleBar,
                    display: "flex",
                    alignItems: "center",
                    gap: 16,
                    padding: "0 24px",
                    color: palette.white
                }, children: [_jsx("div", { style: {
                            width: 6,
                            height: 6,
                            borderRadius: 999,
                            background: palette.accent,
                            boxShadow: "0 0 8px rgba(244,114,182,0.58)"
                        } }), _jsx("div", { style: {
                            width: 28,
                            height: 28,
                            borderRadius: 999,
                            background: palette.accent,
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                            fontFamily: fonts.body,
                            fontSize: 12,
                            fontWeight: 800,
                            flexShrink: 0
                        }, children: activeIndex > 0 ? String(activeIndex).padStart(2, "0") : "尾" }), _jsx("div", { style: {
                            flex: 1,
                            fontFamily: fonts.body,
                            fontSize: 14,
                            fontWeight: 500,
                            letterSpacing: 0.2,
                            lineHeight: 1.25,
                            display: "block",
                            overflow: "hidden"
                        }, children: lowerText }), _jsx("div", { style: {
                            fontFamily: fonts.body,
                            fontSize: 12,
                            color: "rgba(255,255,255,0.35)",
                            letterSpacing: 1,
                            marginLeft: "auto",
                            flexShrink: 0
                        }, children: "AI\u901F\u9012" })] })] }));
};
