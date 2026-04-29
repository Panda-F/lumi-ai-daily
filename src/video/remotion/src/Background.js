import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import { palette } from "./theme";
export const Background = () => {
    const frame = useCurrentFrame();
    const offset = (frame * 0.22) % 112;
    const sheenOffset = (frame * 0.85) % 2400;
    return (_jsxs(AbsoluteFill, { style: {
            background: `linear-gradient(135deg, ${palette.bg} 0%, ${palette.bgSoft} 55%, ${palette.bgAlt} 100%)`,
            overflow: "hidden"
        }, children: [_jsx("div", { style: {
                    position: "absolute",
                    inset: 0,
                    backgroundImage: "linear-gradient(rgba(244,114,182,0.04) 1px, transparent 1px), linear-gradient(90deg, rgba(244,114,182,0.04) 1px, transparent 1px)",
                    backgroundSize: "56px 56px",
                    transform: `translate(${offset}px, 0)`
                } }), _jsx("div", { style: {
                    position: "absolute",
                    top: -120,
                    left: -80,
                    width: 700,
                    height: 700,
                    borderRadius: 999,
                    filter: "blur(70px)",
                    background: "rgba(244,114,182,0.09)"
                } }), _jsx("div", { style: {
                    position: "absolute",
                    right: 200,
                    bottom: -60,
                    width: 500,
                    height: 500,
                    borderRadius: 999,
                    filter: "blur(70px)",
                    background: "rgba(192,132,252,0.07)"
                } }), _jsx("div", { style: {
                    position: "absolute",
                    top: 220,
                    right: -100,
                    width: 400,
                    height: 400,
                    borderRadius: 999,
                    filter: "blur(76px)",
                    background: "rgba(251,146,60,0.05)"
                } }), _jsx("div", { style: {
                    position: "absolute",
                    top: -260,
                    left: sheenOffset - 1600,
                    width: 960,
                    height: 1600,
                    transform: "rotate(18deg)",
                    background: "linear-gradient(180deg, rgba(255,255,255,0) 0%, rgba(255,255,255,0.22) 45%, rgba(255,255,255,0) 100%)"
                } })] }));
};
