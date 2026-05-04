import React from "react";
import { Html5Video, Img, staticFile } from "remotion";
import type { MediaKind } from "./types";
import type { IconName } from "./icons";

export const CATEGORIES = ["开场", "开发生态", "平台策略", "产品应用", "行业动态", "研究追踪"] as const;

export const stripLeadDecor = (text: string) =>
  text.replace(/^[^A-Za-z0-9\u4e00-\u9fff]+/u, "").replace(/\s+/g, " ").trim();

export const shortenLabel = (text: string, maxChars: number) => {
  const cleaned = stripLeadDecor(text);
  if (cleaned.length <= maxChars) {
    return cleaned;
  }
  return cleaned.slice(0, Math.max(1, maxChars)).trim();
};

export const inferCategory = (title: string, kind: string) => {
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

export const inferIcon = (title: string, kind: string): IconName => {
  const cleaned = stripLeadDecor(title);
  if (/Claude|模型|推理|长任务/i.test(cleaned)) {
    return "brain";
  }
  if (/LiteParse|解析|文档|OCR/i.test(cleaned)) {
    return "puzzle";
  }
  if (/Qwen|激活成本|开源/i.test(cleaned)) {
    return "settings";
  }
  if (/Codex|开发流程|电脑/i.test(cleaned)) {
    return "monitor";
  }
  if (/Hugging Face|多模态|检索|微调/i.test(cleaned)) {
    return "flask";
  }
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

export const renderMedia = (
  src?: string | null,
  kind?: MediaKind | null,
  fit: "cover" | "contain" = "cover",
  options?: { playbackRate?: number }
) => {
  if (!src) {
    return null;
  }
  const resolved = staticFile(src);
  const lower = resolved.toLowerCase();
  const playbackRate = options?.playbackRate ?? 1;
  if (kind === "video" || lower.endsWith(".mp4") || lower.endsWith(".webm") || lower.endsWith(".mov")) {
    return (
      <Html5Video
        src={resolved}
        muted
        loop
        playsInline
        playbackRate={playbackRate}
        style={{ width: "100%", height: "100%", objectFit: fit }}
      />
    );
  }
  if (lower.endsWith(".gif")) {
    return <Img src={resolved} style={{ width: "100%", height: "100%", objectFit: fit }} />;
  }
  return <Img src={resolved} style={{ width: "100%", height: "100%", objectFit: fit }} />;
};
