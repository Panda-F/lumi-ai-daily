import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { AbsoluteFill } from "remotion";
import { CATEGORIES } from "./helpers";
import { fonts, palette } from "./theme";
export const Header = ({ dateLabel, issueLabel, activeCategory, activeIndex, totalItems }) => {
    return (_jsxs(AbsoluteFill, { style: {
            height: 98,
            boxSizing: "border-box",
            pointerEvents: "none"
        }, children: [_jsxs("div", { style: {
                    height: 58,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    background: "rgba(255,255,255,0.85)",
                    borderBottom: "1px solid rgba(244,114,182,0.18)",
                    backdropFilter: "blur(12px)"
                }, children: [_jsxs("div", { style: {
                            display: "inline-flex",
                            alignItems: "center",
                            gap: 12,
                            padding: "0 24px 0 28px",
                            height: "100%"
                        }, children: [_jsx("div", { style: {
                                    padding: "6px 18px",
                                    borderRadius: 8,
                                    color: palette.white,
                                    background: `linear-gradient(135deg, ${palette.accent} 0%, ${palette.purple} 100%)`,
                                    fontFamily: fonts.display,
                                    fontSize: 13,
                                    fontWeight: 800
                                }, children: "AI\u901F\u9012" }), _jsx("div", { style: {
                                    fontFamily: fonts.body,
                                    fontSize: 12,
                                    fontWeight: 700,
                                    color: palette.weakText,
                                    letterSpacing: 0.8
                                }, children: "LUMI \u65E9\u5B89\u64AD\u62A5" })] }), _jsxs("div", { style: {
                            position: "absolute",
                            left: "50%",
                            top: 16,
                            transform: "translateX(-50%)",
                            display: "flex",
                            alignItems: "center",
                            gap: 9
                        }, children: [Array.from({ length: totalItems }).map((_, index) => {
                                const isActive = index + 1 === activeIndex;
                                return (_jsx("div", { style: {
                                        width: isActive ? 12 : 8,
                                        height: isActive ? 12 : 8,
                                        borderRadius: 999,
                                        background: isActive ? palette.accent : "rgba(244,114,182,0.22)",
                                        boxShadow: isActive ? "0 0 10px rgba(244,114,182,0.42)" : "none"
                                    } }, `header-dot-${index + 1}`));
                            }), _jsx("div", { style: {
                                    marginLeft: 8,
                                    fontFamily: fonts.body,
                                    fontSize: 12,
                                    fontWeight: 700,
                                    color: palette.weakText,
                                    letterSpacing: 0.6
                                }, children: activeIndex > 0 ? `${String(activeIndex).padStart(2, "0")} / ${String(totalItems).padStart(2, "0")}` : "INTRO" })] }), _jsxs("div", { style: {
                            fontFamily: fonts.body,
                            fontSize: 13,
                            color: palette.weakText,
                            display: "flex",
                            gap: 12,
                            alignItems: "center",
                            height: "100%",
                            padding: "0 28px 0 24px"
                        }, children: [_jsx("span", { style: { color: palette.deep, fontWeight: 700 }, children: dateLabel }), _jsx("span", { children: issueLabel })] })] }), _jsx("div", { style: {
                    height: 40,
                    display: "grid",
                    gridTemplateColumns: `repeat(${CATEGORIES.length}, minmax(0, 1fr))`,
                    borderBottom: `1px solid rgba(244,114,182,0.18)`,
                    background: "rgba(255,255,255,0.70)",
                    backdropFilter: "blur(12px)"
                }, children: CATEGORIES.map((category) => {
                    const active = category === activeCategory;
                    return (_jsx("div", { style: {
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                            fontFamily: fonts.body,
                            fontSize: 13,
                            fontWeight: active ? 800 : 600,
                            color: active ? palette.deep : palette.muted,
                            borderRight: `1px solid rgba(244,114,182,0.12)`,
                            background: active ? "rgba(244,114,182,0.10)" : "transparent"
                        }, children: category }, category));
                }) })] }));
};
