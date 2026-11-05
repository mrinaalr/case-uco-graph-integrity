"""The source documents as located passages, from a folder of PDFs or text files and nothing else.

A passage is one sentence (graphkit.sentences_of) with its document, 1-based sentence number and character offsets in
the document's text; `blocks` reads each run of mail-header lines (From:, To:, Cc:, Subject:, Date:) as one passage,
located from its first line to its last. The same splitting the hook and the selector used (llm.passages,
hook.header_blocks), without the case's document list: documents are the files in the folder, in natural order."""

from __future__ import annotations

import re
from pathlib import Path

from graphkit import pdf_text, sentences_of
from reconcile import keys

HEADER = re.compile(r"^(From|To|Cc|Subject|Date):")
FIELD = re.compile(r"(From|To|Cc|Subject|Date):\s*(.*?)(?=\s+(?:From|To|Cc|Subject|Date):|$)")


def natural(path: Path) -> tuple:
    return tuple(int(t) if t.isdigit() else t for t in re.split(r"(\d+)", path.stem))


def document_files(docs: Path, source: str = "pdf") -> list[Path]:
    """The documents: *.pdf, or the *.txt files whose stem has no second extension (derived text files are skipped)."""
    if source == "pdf":
        files = [p for p in docs.glob("*.pdf")]
    else:
        files = [p for p in docs.glob("*.txt") if "." not in p.stem]
    return sorted(files, key=natural)


def document_text(path: Path) -> str:
    return (pdf_text(path) if path.suffix == ".pdf" else path.read_text(encoding="utf-8")).strip()


class Source:
    """One case's documents: `docs` (id -> text), `passages` (sentences), `blocks` (mail headers folded), `headers`
    (each header block's fields by Subject: line), and the grounding index over `blocks`."""

    def __init__(self, docs_dir: Path, source: str = "pdf") -> None:
        self.files = document_files(docs_dir, source)
        self.docs = {p.stem: document_text(p) for p in self.files}
        self.passages = self._passages()
        self.blocks = header_blocks(self.passages)
        self.headers = headers(self.blocks)
        self.index = keys.index(self.blocks)
        self.at = {(p["doc"], p["sentence"]): i for i, p in enumerate(self.blocks)}

    def _passages(self) -> list[dict]:
        out = []
        for doc_id, text in self.docs.items():
            pos = 0
            for i, sentence in enumerate(sentences_of(text), 1):
                m = re.compile(r"\s+".join(map(re.escape, sentence.split()))).search(text, pos)
                pos = m.end() if m else pos
                out.append({"doc": doc_id, "sentence": i, "start": m.start() if m else None,
                            "end": m.end() if m else None, "text": sentence})
        return out

    def passage_index(self, p: dict) -> int | None:
        """The index in `blocks` of a retrieved passage (by document and sentence number)."""
        return self.at.get((p["doc"], p["sentence"]))

    def is_header(self, i: int) -> bool:
        return bool(HEADER.match(self.blocks[i]["text"]))


def header_blocks(passages: list[dict]) -> list[dict]:
    """Each run of consecutive mail-header lines as one passage."""
    out, prev = [], None
    for p in passages:
        if HEADER.match(p["text"]) and prev == (p["doc"], p["sentence"] - 1):
            out[-1] = {**out[-1], "end": p["end"], "text": f"{out[-1]['text']} {p['text']}"}
        else:
            out.append(p)
        prev = (p["doc"], p["sentence"]) if HEADER.match(p["text"]) else None
    return out


def cite(p: dict | None) -> dict | None:
    return {k: p[k] for k in ("doc", "sentence", "start", "end", "text")} if p else None


def headers(blocks: list[dict]) -> dict[str, list[dict]]:
    """Each mail-header block's fields and location, by its Subject: line (lowercased, spaces collapsed)."""
    out: dict[str, list[dict]] = {}
    for p in blocks:
        fields = dict(FIELD.findall(p["text"])) if HEADER.match(p["text"]) else {}
        if "Subject" in fields:
            out.setdefault(" ".join(fields["Subject"].lower().split()), []).append({**fields, "at": cite(p)})
    return out
