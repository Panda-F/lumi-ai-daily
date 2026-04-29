import fs from "node:fs";
import path from "node:path";
import { bundle } from "@remotion/bundler";
import { renderStill, selectComposition } from "@remotion/renderer";

const entryPoint = path.resolve("./src/index.ts");
const bundleOutDir = path.resolve("./.bundle-layout-stress");
const publicDir = path.resolve("./public");
const outDir = path.resolve(process.argv[2] ?? "./layout-stress-output");
const INTRO_MEDIA = "generated/2026-04-15/media/02-02-11-cdn.prod.website-files.com-6914d00328fde4187dc9cdbe_claude-code_vs-code_preview-p-1600.webp";
const DETAIL_MEDIA = "generated/2026-04-13/media/03-01-openai-enterprise-frontier-layer.png";

const makeIntroScene = (itemCount) => ({
  id: "intro",
  kind: "intro",
  start_frame: 0,
  end_frame: 180,
  duration_frames: 180,
  still_frame: 90,
  script: "",
  oral_script: "",
  subtitle_script: "",
  words: [],
  subtitle_cues: [],
  layout_variant: "intro",
  template_variant: "intro_light",
  shot_regions: [],
  media_assets: [],
  date_label: "2026.04.16",
  item_count_label: `今日 ${itemCount} 条`,
  issue_label: `第 24 期`,
  title: "AI速递",
  subtitle: `2026.04.16 · 今日 ${itemCount} 条`,
  trend_words: ["企业 AI", "工作流入口", "采购决策"],
  headlines: Array.from({ length: itemCount }, (_, index) => `第 ${index + 1} 条`),
  opening: "",
  agenda: "",
  transition: "",
  agenda_lines: Array.from({ length: itemCount }, (_, index) =>
    `OpenAI 企业入口控制层升级 ${index + 1}：把超长工作流标题、治理、评估和 Agent 统一到一套控制面。`
  ),
  lead_title: "企业 AI，已经进入谁控制使用入口的阶段",
  lead_media_src: INTRO_MEDIA,
  primary_media_src: INTRO_MEDIA,
  primary_media_kind: "image",
  lumi_intro_src: null,
  lumi_intro_kind: null
});

const makeItemScene = (index, totalItems, startFrame) => ({
  id: `item-${index + 1}`,
  kind: "item",
  start_frame: startFrame,
  end_frame: startFrame + 180,
  duration_frames: 180,
  still_frame: startFrame + 90,
  script: "",
  oral_script: "",
  subtitle_script: "",
  words: [],
  subtitle_cues: [],
  layout_variant: "fact_card",
  template_variant: "media_then_quote",
  shot_regions: [],
  media_assets: [
    {
      src: DETAIL_MEDIA,
      kind: "image",
      source_domain: "openai.com",
      priority: 0
    }
  ],
  primary_media_src: DETAIL_MEDIA,
  primary_media_kind: "image",
  item_kind: "analysis",
  index,
  current_index: index + 1,
  total_items: totalItems,
  title: `超长标题 ${index + 1}：OpenAI Enterprise Workflow Orchestrator Control Plane ${index + 1}`,
  display_title: `超长标题 ${index + 1}：OpenAI Enterprise Workflow Orchestrator Control Plane 把模型、Agent、治理、上下文重新装进一个入口产品里`,
  spoken_title: `超长标题 ${index + 1}`,
  spoken_aliases: [],
  short_title: `超长标题 ${index + 1}`,
  content:
    "企业买单的重心已经从单点模型能力，转到能不能直接接住工作流、权限、治理和默认入口。这段文字故意拉长，用来压测主卡正文在高密度情况下的缩放和裁切。",
  interpretation:
    "如果默认入口被一个工作台拿走，后面的模型、Agent、评估和内部知识库都会被打包成一个采购决策。这里继续故意拉长，用来验证右侧解释卡和底部信息卡不会互相顶穿。",
  quote:
    "真正值钱的不是模型本身，而是谁先成为团队默认打开的那一层入口产品。",
  hook:
    "入口一旦被占住，后面的调用、评估、治理和留存就会顺着它走。",
  takeaway:
    "采购重点正在从谁最强，变成谁最容易落地、治理和接进真实流程。",
  fact_points: [
    "产品入口、Agent 执行、评估和上下文正在被重新打包进一套购买叙事。",
    "企业决策会优先选择部署阻力小、权限治理明确、组织协作链路顺的产品层。",
    "默认入口权会继续影响上层分发和下游留存。"
  ],
  source_note: "The Information / 企业软件与 AI 工作流追踪 / 多源综合",
  outro:
    "接下来继续观察谁能真正拿到日常工作的默认入口，以及这会怎样反过来影响模型层分发。",
  source_domain: "theinformation.com",
  source_url: "https://example.com/story",
  status: null,
  card_type: "text",
  image_src: null,
  image_srcs: [],
  media_usage: "",
  media_reject_reason: null,
  style_variant: "media_then_quote"
});

const makeOutroScene = (itemCount, startFrame) => ({
  id: "outro",
  kind: "outro",
  start_frame: startFrame,
  end_frame: startFrame + 180,
  duration_frames: 180,
  still_frame: startFrame + 90,
  script: "",
  oral_script: "",
  subtitle_script: "",
  words: [],
  subtitle_cues: [],
  layout_variant: "fact_card",
  template_variant: "outro_light",
  shot_regions: [],
  media_assets: [],
  primary_media_src: null,
  primary_media_kind: null,
  line_one: "Lumi明天继续陪你看",
  line_two: "",
  quote_text: `今天一共 ${itemCount} 条，继续关注入口、治理和企业工作流。`,
  quote_translation: "",
  quote_author: "Lumi"
});

const makeManifest = (itemCount) => {
  const intro = makeIntroScene(itemCount);
  const items = Array.from({ length: itemCount }, (_, index) => makeItemScene(index, itemCount, 180 + index * 180));
  const outroStart = 180 + itemCount * 180;
  const outro = makeOutroScene(itemCount, outroStart);
  const totalFrames = outro.end_frame;

  return {
    renderer: "remotion",
    version: 1,
    meta: {
      date: "2026.04.16",
      title: "AI速递",
      issue_label: `今日 ${itemCount} 条`,
      item_count: itemCount,
      total_frames: totalFrames,
      width: 1920,
      height: 1080,
      design_width: 1920,
      design_height: 1080,
      aspect_ratio: "16:9",
      fps: 60,
      layout: "daily_report",
      intro_style: "lumi_v3",
      subtitle_mode: "single_line",
      lumi_avatar_src: null,
      primary_hook: "企业 AI 的竞争，已经从模型能力转向入口控制层",
      issue_quote_text: "预测未来最好的方式，就是亲手创造它。",
      issue_quote_author: "Alan Kay"
    },
    report: {
      trend_words: ["企业 AI", "入口争夺", "工作流"],
      items: Array.from({ length: itemCount }, (_, index) => ({
        index: index + 1,
        title: `超长标题 ${index + 1}：OpenAI Enterprise Workflow Orchestrator Control Plane 把模型、Agent、治理、上下文重新装进一个入口产品里`,
        source_url: "https://example.com/story"
      }))
    },
    scenes: [intro, ...items, outro]
  };
};

const scenarios = [
  { name: "dense-8", manifest: makeManifest(8) },
  { name: "dense-10", manifest: makeManifest(10) }
];

fs.mkdirSync(outDir, { recursive: true });
fs.rmSync(bundleOutDir, { recursive: true, force: true });

const bundled = await bundle({
  entryPoint,
  outDir: bundleOutDir,
  publicDir,
  rootDir: path.resolve("."),
  webpackOverride: (config) => config
});

for (const child of fs.readdirSync(publicDir)) {
  const source = path.join(publicDir, child);
  const destination = path.join(bundleOutDir, child);
  fs.cpSync(source, destination, { recursive: true, force: true });
}

const outputs = [];

for (const scenario of scenarios) {
  const composition = await selectComposition({
    serveUrl: bundled,
    id: "DailyReport",
    inputProps: { manifest: scenario.manifest }
  });

  const frames = [
    { suffix: "cover", frame: 24 },
    { suffix: "opening-1", frame: 96 },
    ...(scenario.manifest.meta.item_count > 8 ? [{ suffix: "opening-2", frame: 146 }] : []),
    { suffix: "item-first-opener", frame: 258 },
    { suffix: "item-first-detail", frame: 336 },
    { suffix: "item-last-opener", frame: 180 + (scenario.manifest.meta.item_count - 1) * 180 + 78 },
    { suffix: "item-last-detail", frame: 180 + (scenario.manifest.meta.item_count - 1) * 180 + 156 },
    { suffix: "outro", frame: scenario.manifest.meta.total_frames - 90 }
  ];

  for (const still of frames) {
    const output = path.join(outDir, `${scenario.name}-${still.suffix}.png`);
    await renderStill({
      composition,
      serveUrl: bundled,
      inputProps: { manifest: scenario.manifest },
      output,
      frame: still.frame,
      imageFormat: "png"
    });
    outputs.push(output);
  }
}

console.log(
  JSON.stringify(
    {
      result: "success",
      outDir,
      files: outputs
    },
    null,
    2
  )
);
