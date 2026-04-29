import { jsx as _jsx } from "react/jsx-runtime";
import { Html5Video, Img, staticFile } from "remotion";
export const CATEGORIES = ["早安", "开发生态", "平台策略", "产品应用", "行业动态", "研究追踪"];
export const stripLeadDecor = (text) => text.replace(/^[^A-Za-z0-9\u4e00-\u9fff]+/u, "").replace(/\s+/g, " ").trim();
export const shortenLabel = (text, maxChars) => {
    const cleaned = stripLeadDecor(text);
    if (cleaned.length <= maxChars) {
        return cleaned;
    }
    return cleaned.slice(0, Math.max(1, maxChars)).trim();
};
export const inferCategory = (title, kind) => {
    const cleaned = stripLeadDecor(title);
    if (kind === "research" || /LPM|Meta-Harness|DMax|论文|研究|Diffusion/i.test(cleaned)) {
        return "研究追踪";
    }
    if (/风险|风控|供应商|封禁|生态/.test(cleaned)) {
        return "行业动态";
    }
    if (/Music|配乐|音乐|产品|应用|视频|品牌/i.test(cleaned)) {
        return "产品应用";
    }
    if (/规划|执行|云端|本地|战略|边界/.test(cleaned)) {
        return "平台策略";
    }
    if (/Code|内核|提交流程|运维|开发|协作/i.test(cleaned)) {
        return "开发生态";
    }
    return "开发生态";
};
export const inferIcon = (title, kind) => {
    const cleaned = stripLeadDecor(title);
    if (kind === "research" || /LPM|Meta-Harness|DMax|论文|研究/i.test(cleaned)) {
        return "masks";
    }
    if (/Music|配乐|音乐/i.test(cleaned)) {
        return "music-4";
    }
    if (/风险|风控|供应商/i.test(cleaned)) {
        return "shield-alert";
    }
    if (/Claude Code|规划|云端/i.test(cleaned)) {
        return "cloud";
    }
    if (/Linux|内核|提交流程|文档/i.test(cleaned)) {
        return "file-text";
    }
    return "smartphone";
};
export const renderMedia = (src, kind, fit = "cover") => {
    if (!src) {
        return null;
    }
    const resolved = staticFile(src);
    if (kind === "gif" || kind === "video" || resolved.endsWith(".mp4") || resolved.endsWith(".webm")) {
        return (_jsx(Html5Video, { src: resolved, muted: true, loop: true, playsInline: true, style: { width: "100%", height: "100%", objectFit: fit } }));
    }
    return _jsx(Img, { src: resolved, style: { width: "100%", height: "100%", objectFit: fit } });
};
