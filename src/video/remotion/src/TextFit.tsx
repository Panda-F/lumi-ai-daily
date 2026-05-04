import React from "react";

type FitOptions = {
  maxWidth: number;
  maxFontSize: number;
  minFontSize: number;
  maxLines: number;
};

const normalizeText = (text: string) => (text || "").replace(/\s+/g, " ").trim();

const visualUnits = (text: string) => {
  let units = 0;
  for (const char of text || "") {
    if (/\s/u.test(char)) units += 0.32;
    else if (/[\u4e00-\u9fff]/u.test(char)) units += 1;
    else if (/[A-Z]/u.test(char)) units += 0.68;
    else if (/[a-z0-9]/u.test(char)) units += 0.56;
    else units += 0.42;
  }
  return Math.max(units, 1);
};

const segmentText = (text: string) => {
  const cleaned = normalizeText(text);
  if (!cleaned) {
    return [];
  }
  try {
    const Segmenter = (Intl as any).Segmenter;
    const segmenter = new Segmenter("zh", { granularity: "word" });
    return Array.from(segmenter.segment(cleaned) as Iterable<{ segment: string }>)
      .map((segment) => segment.segment.trim())
      .filter(Boolean);
  } catch {
    return cleaned.match(/[A-Za-z0-9][A-Za-z0-9.+/#-]*|[\u4e00-\u9fff]{1,4}|[^\s]/gu) || [cleaned];
  }
};

const tokenSeparator = (previous: string, token: string) => {
  if (
    (/[A-Za-z0-9]$/u.test(previous) && /^[A-Za-z0-9]/u.test(token)) ||
    (/[,.;:!?]$/u.test(previous) && /^[A-Za-z0-9]/u.test(token))
  ) {
    return " ";
  }
  return "";
};

const joinTokens = (tokens: string[]) => {
  let value = "";
  for (const token of tokens) {
    value = value ? `${value}${tokenSeparator(value, token)}${token}` : token;
  }
  return value;
};

const balancedLines = (text: string, maxLines: number, unitsPerLine: number) => {
  const tokens = segmentText(text);
  if (!tokens.length) {
    return [normalizeText(text)];
  }
  const lines: string[] = [];
  let current = "";
  let currentUnits = 0;
  for (const token of tokens) {
    const tokenUnits = visualUnits(token);
    const separator = current ? tokenSeparator(current, token) : "";
    const nextUnits = currentUnits + visualUnits(separator) + tokenUnits;
    if (current && nextUnits > unitsPerLine && lines.length < maxLines - 1) {
      lines.push(current);
      current = token;
      currentUnits = tokenUnits;
    } else {
      current = `${current}${separator}${token}`;
      currentUnits = nextUnits;
    }
  }
  if (current) {
    lines.push(current);
  }

  while (lines.length > 1 && visualUnits(lines[lines.length - 1]) < 3) {
    const previous = lines[lines.length - 2];
    const previousTokens = segmentText(previous);
    if (previousTokens.length <= 1) {
      break;
    }
    const moved = previousTokens.pop() as string;
    lines[lines.length - 2] = joinTokens(previousTokens);
    lines[lines.length - 1] = `${moved}${lines[lines.length - 1]}`;
  }
  return lines;
};

export const fitText = (text: string, options: FitOptions) => {
  const cleaned = normalizeText(text);
  const totalUnits = visualUnits(cleaned);
  for (let size = options.maxFontSize; size >= options.minFontSize; size -= 2) {
    if (totalUnits * size <= options.maxWidth * 0.96) {
      return { fontSize: size, lines: [cleaned] };
    }
  }
  const wrappedFontSize = Math.max(
    options.minFontSize,
    Math.min(options.maxFontSize, Math.floor((options.maxWidth * options.maxLines * 0.9) / totalUnits))
  );
  const lines = balancedLines(cleaned, options.maxLines, (options.maxWidth / wrappedFontSize) * 0.92);
  return { fontSize: wrappedFontSize, lines };
};

export const FitTextBlock: React.FC<{
  text: string;
  maxWidth: number;
  maxFontSize: number;
  minFontSize: number;
  maxLines: number;
  style?: React.CSSProperties;
  lineHeight?: number;
}> = ({ text, maxWidth, maxFontSize, minFontSize, maxLines, style, lineHeight = 1.08 }) => {
  const fitted = fitText(text, { maxWidth, maxFontSize, minFontSize, maxLines });
  return (
    <div
      style={{
        ...style,
        width: maxWidth,
        maxWidth,
        fontSize: fitted.fontSize,
        lineHeight,
        overflowWrap: "normal",
        wordBreak: "keep-all"
      }}
    >
      {fitted.lines.map((line, index) => (
        <div key={`${line}-${index}`}>{line}</div>
      ))}
    </div>
  );
};
