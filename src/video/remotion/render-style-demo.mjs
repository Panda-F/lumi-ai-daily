import fs from "node:fs";
import path from "node:path";
import { bundle } from "@remotion/bundler";
import { renderStill, selectComposition } from "@remotion/renderer";

const outDir = path.resolve(process.argv[2] ?? "./style-demo-output");
const entryPoint = path.resolve("./src/index.ts");
const bundleOutDir = path.resolve("./.bundle-style-demo");
const publicDir = path.resolve("./public");

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

const specs = [
  { output: path.join(outDir, "style-demo-cover.png"), inputProps: { variant: "cover" } },
  { output: path.join(outDir, "style-demo-opening.png"), inputProps: { variant: "opening", openingCount: 6 } },
  { output: path.join(outDir, "style-demo-story.png"), inputProps: { variant: "story" } },
  { output: path.join(outDir, "style-demo-detail.png"), inputProps: { variant: "detail" } },
  { output: path.join(outDir, "style-demo-outro.png"), inputProps: { variant: "outro" } },
  { output: path.join(outDir, "style-demo-opening-3.png"), inputProps: { variant: "opening", openingCount: 3 } },
  { output: path.join(outDir, "style-demo-opening-6.png"), inputProps: { variant: "opening", openingCount: 6 } },
  { output: path.join(outDir, "style-demo-opening-8.png"), inputProps: { variant: "opening", openingCount: 8 } }
];

for (const spec of specs) {
  const composition = await selectComposition({
    serveUrl: bundled,
    id: "StyleDemo",
    inputProps: spec.inputProps
  });

  await renderStill({
    composition,
    serveUrl: bundled,
    inputProps: spec.inputProps,
    output: spec.output,
    frame: 48,
    imageFormat: "png"
  });
}

console.log(
  JSON.stringify(
    {
      result: "success",
      outDir,
      files: specs.map((spec) => spec.output)
    },
    null,
    2
  )
);
