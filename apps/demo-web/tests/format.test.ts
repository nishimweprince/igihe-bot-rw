import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { citedNumbers, decodeEntities, parseBlocks, parseInline, plainText } from "../lib/format.ts";

describe("parseInline", () => {
  it("turns [n] markers into cite tokens and trims the space before them", () => {
    assert.deepEqual(parseInline("Abahinga bazacibwa amande [1]."), [
      { kind: "text", text: "Abahinga bazacibwa amande" },
      { kind: "cite", n: 1 },
      { kind: "text", text: "." },
    ]);
  });

  it("expands grouped citations like [1, 3]", () => {
    assert.deepEqual(parseInline("Byemejwe [1, 3]."), [
      { kind: "text", text: "Byemejwe" },
      { kind: "cite", n: 1 },
      { kind: "cite", n: 3 },
      { kind: "text", text: "." },
    ]);
  });

  it("renders **bold** spans", () => {
    assert.deepEqual(parseInline("Ni **ingenzi** cyane"), [
      { kind: "text", text: "Ni " },
      { kind: "strong", text: "ingenzi" },
      { kind: "text", text: " cyane" },
    ]);
  });

  it("leaves plain text untouched", () => {
    assert.deepEqual(parseInline("Mbabarira, nta bimenyetso bihagije."), [
      { kind: "text", text: "Mbabarira, nta bimenyetso bihagije." },
    ]);
  });

  it("turns [label](https://...) into link tokens", () => {
    assert.deepEqual(parseInline("Reba kuri [IGIHE](https://igihe.com)."), [
      { kind: "text", text: "Reba kuri " },
      { kind: "link", text: "IGIHE", url: "https://igihe.com" },
      { kind: "text", text: "." },
    ]);
  });

  it("keeps [n] citations working next to links", () => {
    assert.deepEqual(parseInline("Reba [IGIHE](https://igihe.com), amande [1]."), [
      { kind: "text", text: "Reba " },
      { kind: "link", text: "IGIHE", url: "https://igihe.com" },
      { kind: "text", text: ", amande" },
      { kind: "cite", n: 1 },
      { kind: "text", text: "." },
    ]);
  });

  it("leaves non-http link lookalikes as plain text", () => {
    assert.deepEqual(parseInline("Reba [IGIHE](igihe.com)."), [
      { kind: "text", text: "Reba [IGIHE](igihe.com)." },
    ]);
  });
});

describe("parseBlocks", () => {
  it("splits paragraphs on blank lines and keeps single newlines as breaks", () => {
    const blocks = parseBlocks("Umurongo wa mbere\numurongo wa kabiri\n\nIgika cya kabiri [2].");
    assert.equal(blocks.length, 2);
    assert.equal(blocks[0]?.kind, "p");
    assert.ok(blocks[0]?.kind === "p" && blocks[0].inlines.some((i) => i.kind === "br"));
    assert.equal(blocks[1]?.kind, "p");
  });

  it("recognises bullet and numbered lists", () => {
    const blocks = parseBlocks("- Imwe [1]\n- Ebyiri [2]\n\n1. Mbere\n2) Kabiri");
    assert.equal(blocks[0]?.kind, "ul");
    assert.equal(blocks[1]?.kind, "ol");
    assert.ok(blocks[0]?.kind === "ul" && blocks[0].items.length === 2);
  });

  it("returns nothing for empty input", () => {
    assert.deepEqual(parseBlocks("   \n\n"), []);
  });
});

describe("citedNumbers", () => {
  it("lists distinct citation numbers in order of first appearance", () => {
    assert.deepEqual(citedNumbers("A [2]. B [1]. C [2, 3]."), [2, 1, 3]);
  });
});

describe("decodeEntities", () => {
  it("decodes numeric and named entities left in WordPress titles", () => {
    assert.equal(decodeEntities("C&#244;te d&#8217;Ivoire &amp; Kigali &#x27;s"), "Côte d’Ivoire & Kigali 's");
  });

  it("leaves unknown entities alone", () => {
    assert.equal(decodeEntities("a &bogus; b"), "a &bogus; b");
  });
});

describe("plainText", () => {
  it("strips bold markers but keeps citations for copying", () => {
    assert.equal(plainText("Ni **ingenzi** [1]. "), "Ni ingenzi [1].");
  });

  it("expands links to label plus url for copying", () => {
    assert.equal(
      plainText("Reba kuri [IGIHE](https://igihe.com). "),
      "Reba kuri IGIHE (https://igihe.com).",
    );
  });
});
