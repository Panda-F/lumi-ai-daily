import fs from "node:fs";
import path from "node:path";
import { bundle } from "@remotion/bundler";
import { renderMedia, renderStill, selectComposition } from "@remotion/renderer";

const parseArgs = () => {
  const raw = process.argv.slice(2);
  const result = {};
  for (let index = 0; index < raw.length; index += 2) {
    result[raw[index]] = raw[index + 1];
  }
  return result;
};

const must = (value, flag) => {
  if (!value) {
    throw new Error(`Missing required argument: ${flag}`);
  }
  return value;
};

const args = parseArgs();
const manifestPath = path.resolve(must(args["--manifest"], "--manifest"));
const stillSpecsPath = path.resolve(must(args["--stills"], "--stills"));
const outputPath = args["--video"] ? path.resolve(args["--video"]) : null;
const publicDir = args["--public-dir"] ? path.resolve(args["--public-dir"]) : path.resolve("./public");

const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
const stillSpecs = JSON.parse(fs.readFileSync(stillSpecsPath, "utf8"));

const entryPoint = path.resolve("./src/index.ts");
const bundleOutDir = path.resolve("./.bundle");
fs.rmSync(bundleOutDir, { recursive: true, force: true });
fs.mkdirSync(publicDir, { recursive: true });
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

const composition = await selectComposition({
  serveUrl: bundled,
  id: "DailyReport",
  inputProps: { manifest }
});

let lastLoggedPercent = -5;
if (outputPath) {
  await renderMedia({
    composition,
    serveUrl: bundled,
    codec: "h264",
    outputLocation: outputPath,
    inputProps: { manifest },
    concurrency: 3,
    disallowParallelEncoding: false,
    timeoutInMilliseconds: 120000,
    logLevel: "info",
    x264Preset: "veryfast",
    jpegQuality: 75,
    mediaCacheSizeInBytes: 768 * 1024 * 1024,
    onStart: ({ frameCount, resolvedConcurrency, parallelEncoding }) => {
      console.log(
        JSON.stringify({
          stage: "render-start",
          frameCount,
          resolvedConcurrency,
          parallelEncoding
        })
      );
    },
    onProgress: ({ progress, renderedFrames, encodedFrames, stitchStage, renderedDoneIn, encodedDoneIn }) => {
      const percent = Math.floor(progress * 100);
      if (percent >= lastLoggedPercent + 5 || renderedDoneIn !== null || encodedDoneIn !== null) {
        lastLoggedPercent = percent;
        console.log(
          JSON.stringify({
            stage: "render-progress",
            percent,
            renderedFrames,
            encodedFrames,
            stitchStage,
            renderedDoneIn,
            encodedDoneIn
          })
        );
      }
    },
    onBrowserLog: (log) => {
      if (log.type === "error" || log.type === "warn") {
        console.error(
          JSON.stringify({
            stage: "browser-log",
            type: log.type,
            text: log.text,
            stackTrace: log.stackTrace ?? null
          })
        );
      }
    }
  });
} else {
  console.log(JSON.stringify({ stage: "render-media-skip", reason: "no-video-output" }));
}

for (const still of stillSpecs) {
  await renderStill({
    composition,
    serveUrl: bundled,
    inputProps: { manifest },
    output: still.output,
    frame: still.frame,
    imageFormat: "png"
  });
}

console.log(
  JSON.stringify(
    {
      result: "success",
      video: outputPath,
      stills: stillSpecs.map((still) => still.output)
    },
    null,
    2
  )
);
