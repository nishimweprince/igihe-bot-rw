/**
 * Lightweight formatter for assistant prose.
 *
 * Answers are short Kinyarwanda sentences that end in `[n]` citations
 * (see src/igihe_assistant/prompting/builder.py). We render those as chips
 * linked to the matching source, and support just enough structure
 * (paragraphs, bullet/numbered lists, **bold**, [label](https://...) links)
 * to keep answers readable
 * without pulling in a markdown dependency.
 */

export type Inline =
  | { kind: "text"; text: string }
  | { kind: "strong"; text: string }
  | { kind: "link"; text: string; url: string }
  | { kind: "cite"; n: number }
  | { kind: "br" };

export type Block =
  | { kind: "p"; inlines: Inline[] }
  | { kind: "ul"; items: Inline[][] }
  | { kind: "ol"; items: Inline[][] };

const INLINE_RE = /(\*\*[^*\n]+\*\*)|(\[[^\]\n]+\]\(https?:\/\/[^\s)]+\))|(\[\d+(?:\s*,\s*\d+)*\])/g;
const LINK_RE = /\[([^\]\n]+)\]\((https?:\/\/[^\s)]+)\)/;
const BULLET_RE = /^\s*[-*•]\s+(.*)$/;
const NUMBERED_RE = /^\s*\d+[.)]\s+(.*)$/;

function pushText(out: Inline[], text: string): void {
  if (!text) return;
  const last = out[out.length - 1];
  if (last && last.kind === "text") {
    last.text += text;
  } else {
    out.push({ kind: "text", text });
  }
}

/** Split one line into text, bold spans and citation chips. */
export function parseInline(line: string): Inline[] {
  const out: Inline[] = [];
  let cursor = 0;
  for (const match of line.matchAll(INLINE_RE)) {
    const start = match.index ?? 0;
    const raw = match[0];
    if (match[1]) {
      pushText(out, line.slice(cursor, start));
      out.push({ kind: "strong", text: raw.slice(2, -2) });
    } else if (match[2]) {
      pushText(out, line.slice(cursor, start));
      const inner = LINK_RE.exec(raw);
      if (inner) out.push({ kind: "link", text: inner[1], url: inner[2] });
      else pushText(out, raw);
    } else {
      // A chip carries its own spacing, so drop the space the model put
      // before "[1]" to keep punctuation tight: "amande [1]." -> "amande[1]."
      pushText(out, line.slice(cursor, start).replace(/\s+$/, ""));
      for (const num of raw.slice(1, -1).split(",")) {
        const n = Number(num.trim());
        if (Number.isFinite(n) && n > 0) out.push({ kind: "cite", n });
      }
    }
    cursor = start + raw.length;
  }
  pushText(out, line.slice(cursor));
  return out;
}

function parseLines(lines: string[]): Inline[] {
  const out: Inline[] = [];
  lines.forEach((line, i) => {
    if (i > 0) out.push({ kind: "br" });
    out.push(...parseInline(line));
  });
  return out;
}

/** Split answer text into paragraphs and lists. */
export function parseBlocks(text: string): Block[] {
  const blocks: Block[] = [];
  const chunks = text
    .replace(/\r\n?/g, "\n")
    .split(/\n{2,}/)
    .map((c) => c.trim())
    .filter(Boolean);

  for (const chunk of chunks) {
    const lines = chunk.split("\n");
    if (lines.every((l) => BULLET_RE.test(l))) {
      blocks.push({ kind: "ul", items: lines.map((l) => parseInline(l.match(BULLET_RE)![1])) });
      continue;
    }
    if (lines.every((l) => NUMBERED_RE.test(l))) {
      blocks.push({ kind: "ol", items: lines.map((l) => parseInline(l.match(NUMBERED_RE)![1])) });
      continue;
    }
    blocks.push({ kind: "p", inlines: parseLines(lines) });
  }
  return blocks;
}

/** Distinct citation numbers in the order they first appear. */
export function citedNumbers(text: string): number[] {
  const seen = new Set<number>();
  for (const block of parseBlocks(text)) {
    const inlines = block.kind === "p" ? block.inlines : block.items.flat();
    for (const inline of inlines) {
      if (inline.kind === "cite") seen.add(inline.n);
    }
  }
  return [...seen];
}

/** Plain-text copy of an answer with citation markers preserved. */
export function plainText(text: string): string {
  return text
    .replace(/\[([^\]\n]+)\]\((https?:\/\/[^\s)]+)\)/g, "$1 ($2)")
    .replace(/\*\*([^*\n]+)\*\*/g, "$1")
    .trim();
}

const NAMED_ENTITIES: Record<string, string> = {
  amp: "&",
  lt: "<",
  gt: ">",
  quot: '"',
  apos: "'",
  nbsp: "\u00a0",
  hellip: "\u2026",
  ndash: "\u2013",
  mdash: "\u2014",
  lsquo: "\u2018",
  rsquo: "\u2019",
  ldquo: "\u201c",
  rdquo: "\u201d",
};

/** Decode HTML entities WordPress leaves in article titles (e.g. `d&#8217;Ivoire`). */
export function decodeEntities(text: string): string {
  return text.replace(/&(#x[0-9a-f]+|#\d+|[a-z]+);/gi, (whole, body: string) => {
    if (body[0] === "#") {
      const code = body[1].toLowerCase() === "x" ? parseInt(body.slice(2), 16) : parseInt(body.slice(1), 10);
      return Number.isFinite(code) ? String.fromCodePoint(code) : whole;
    }
    return NAMED_ENTITIES[body.toLowerCase()] ?? whole;
  });
}
