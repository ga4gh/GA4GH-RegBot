import re
from typing import List, Optional, Tuple

# "Source:", "License:", "Tier:" and similar front-matter keys are not section headings.
_KEY_VALUE_LINE = re.compile(r"^[A-Za-z][A-Za-z ]{0,18}:\s")
_LIST_MARKERS = "-•*·—"
_SENTENCE_BOUNDARY = re.compile(r"[.!?]\s+[A-Z]")

# A heading is a noun phrase; a hard-wrapped body line usually breaks mid-clause on one
# of these. Used to reject wrapped prose that happens to sit between blank lines.
_CONTINUATION_WORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "or",
        "but",
        "of",
        "to",
        "in",
        "on",
        "at",
        "by",
        "for",
        "with",
        "from",
        "as",
        "that",
        "which",
        "who",
        "whom",
        "whose",
        "such",
        "these",
        "this",
        "those",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "has",
        "have",
        "had",
        "may",
        "must",
        "should",
        "will",
        "can",
        "not",
        "any",
        "all",
        "their",
        "its",
        "when",
        "where",
        "while",
        "if",
        "than",
        "then",
        "into",
        "under",
        "over",
    }
)

MAX_HEADING_CHARS = 90

# Page furniture from scraped HTML. These look like headings and are not provisions, so
# they pollute `section` and, through it, the provision keys the benchmark scores against
# (a GA4GH brief was contributing "News — 2 Sep 2019" as a citable section).
_FURNITURE = frozenset(
    {
        "news",
        "blog",
        "events",
        "share",
        "share this",
        "further reading",
        "references",
        "reference",
        "related",
        "related news",
        "related posts",
        "read more",
        "contact",
        "contact us",
        "acknowledgements",
        "acknowledgments",
        "about",
        "about us",
        "authors",
        "author",
        "citation",
        "download",
        "downloads",
        "resources",
        "our products",
        "publications",
        "newsletter",
        "subscribe",
    }
)

# "2 Sep 2019", "September 2019", "2019-09-02" — a date is never a provision.
_DATE_LIKE = re.compile(
    r"^\d{1,2}\s+[A-Za-z]{3,9}\.?\s+\d{4}$"
    r"|^[A-Za-z]{3,9}\.?\s+\d{1,2},?\s+\d{4}$"
    r"|^[A-Za-z]{3,9}\.?\s+\d{4}$"
    r"|^\d{4}[-/]\d{1,2}[-/]\d{1,2}$"
)


def _is_page_furniture(line: str) -> bool:
    """True for scraped-page headings that carry no regulatory content."""
    bare = line.strip().strip(":").strip()
    if bare.lower() in _FURNITURE:
        return True
    if _DATE_LIKE.match(bare):
        return True
    # "News — 2 Sep 2019": furniture label joined to a date.
    for sep in ("—", "–", "-", "|", ":"):
        if sep in bare:
            head, _, tail = bare.partition(sep)
            if head.strip().lower() in _FURNITURE and (
                _DATE_LIKE.match(tail.strip()) or not tail.strip()
            ):
                return True
    return False


def fold_plural(word: str) -> str:
    """
    Fold a regular English plural to its singular. Deliberately narrow.

    Statutes are written in the singular — "A Participant may make a request", "the
    biological specimen" — while questions are asked in the plural — "can participants
    withdraw", "what happens to samples". Without this, BM25 scores those as unrelated
    terms, and the Taiwan withdrawal provision shared exactly one content word with its
    own gold query.

    Only regular plurals are folded, and ``-ss`` / ``-us`` / ``-is`` endings are protected
    so "process", "status" and "analysis" survive intact. No verb or comparative stemming:
    an aggressive stemmer collides distinct legal terms, and the same function normalises
    both the query and the corpus, so a wrong fold would corrupt both sides at once.
    """
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 4 and word.endswith(("sses", "xes", "zes", "ches", "shes")):
        return word[:-2]
    if len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
        return word[:-1]
    return word


def tokenize(text: str) -> List[str]:
    """Tokenize Latin text and CJK text for BM25.

    Latin tokens keep the narrow plural folding used throughout the project. Consecutive
    CJK runs are emitted as overlapping character bigrams, which gives Chinese statutory
    queries lexical recall without adding a segmentation dependency. A single-character
    run is retained so short defined terms are not silently dropped.
    """
    lowered = text.lower()
    tokens = [fold_plural(w) for w in re.findall(r"[a-z0-9]+", lowered)]
    for run in re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]+", lowered):
        if len(run) == 1:
            tokens.append(run)
        else:
            tokens.extend(run[i : i + 2] for i in range(len(run) - 1))
    return tokens


def chunk_spans(
    text: str,
    chunk_size: int = 900,
    overlap: int = 150,
) -> List[Tuple[str, int]]:
    """
    Split text into overlapping chunks, returning ``(chunk, start_offset)`` pairs.

    Offsets are relative to the *stripped* text and let callers map a chunk back to
    structure discovered in the same string (see :func:`detect_headings`).
    """
    text = text.strip()
    if not text:
        return []
    spans: List[Tuple[str, int]] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + chunk_size, n)
        spans.append((text[start:end], start))
        if end >= n:
            break
        start = max(end - overlap, start + 1)
    return spans


def chunk_text(
    text: str,
    chunk_size: int = 900,
    overlap: int = 150,
) -> List[str]:
    return [chunk for chunk, _ in chunk_spans(text, chunk_size, overlap)]


def chunk_by_sections(
    text: str,
    chunk_size: int = 900,
    overlap: int = 150,
    min_chars: int = 120,
) -> List[Tuple[str, int]]:
    """
    Chunk at heading boundaries, falling back to a sliding window inside long sections.

    A fixed-width window cuts statutes mid-provision: GDPR Article 9's prohibition and
    Article 8's child-consent rule land in one 900-character chunk, so a citation spans two
    unrelated obligations and the embedding mixes both topics. Cutting at headings keeps a
    chunk inside one article, which is what a clause-precision tool is supposed to cite.

    Sections longer than ``chunk_size`` are still split — some articles run for pages — but
    every piece stays within the same section. Text before the first heading (front matter)
    forms its own span. Returns ``(chunk, offset)`` like :func:`chunk_spans`, and falls back
    to :func:`chunk_spans` entirely when the document has no detectable headings.
    """
    stripped = text.strip()
    if not stripped:
        return []

    headings = detect_headings(stripped)
    if not headings:
        return chunk_spans(stripped, chunk_size, overlap)

    boundaries = [pos for pos, _ in headings]
    if boundaries[0] > 0:
        boundaries.insert(0, 0)
    boundaries.append(len(stripped))

    out: List[Tuple[str, int]] = []
    pending = ""  # a heading whose own body was empty, waiting to lead the next block
    pending_start = 0
    for start, end in zip(boundaries, boundaries[1:]):
        block = stripped[start:end]
        if not block.strip():
            continue
        if pending:
            block, start = pending + "\n\n" + block, pending_start
            pending, pending_start = "", 0

        # A structural heading with no body of its own — "Section 2 Information and access
        # to personal data" standing alone. Citing it tells a reviewer nothing, so carry it
        # forward to head the next block instead of emitting it as its own chunk.
        if len(block.strip()) < min_chars:
            pending, pending_start = block.strip(), start
            continue

        if len(block) <= chunk_size:
            out.append((block.strip(), start))
            continue
        for piece, rel in chunk_spans(block, chunk_size, overlap):
            out.append((piece, start + rel))

    if pending:
        if out:  # trailing heading with nothing after it
            prev_text, prev_start = out[-1]
            out[-1] = (prev_text + "\n\n" + pending, prev_start)
        else:
            out.append((pending, pending_start))
    return out


def detect_headings(text: str) -> List[Tuple[int, str]]:
    """
    Find section headings in line-structured text, as ``(offset, heading)`` pairs.

    A heading is a short standalone line surrounded by blank lines, without terminal
    punctuation, list markers, or a ``Key: value`` shape. The rule is deliberately strict:
    a wrong ``section`` label on a cited clause is worse for a reviewer than no label, so
    this prefers missing a heading over inventing one.

    Layout-flattened sources (notably ``pypdf`` PDF extraction, which merges heading,
    subheading and body onto one line) yield no headings here. That is intended — such
    chunks get no ``section`` rather than a guessed one.
    """
    stripped = text.strip()
    if not stripped:
        return []
    lines = stripped.split("\n")
    if is_hard_wrapped(lines):
        return []

    found: List[Tuple[int, int, str]] = []  # (line index, offset, text)
    offset = 0
    for i, raw in enumerate(lines):
        line = raw.strip()
        start = offset
        offset += len(raw) + 1
        if not _looks_like_heading(line):
            continue
        prev_blank = i == 0 or not lines[i - 1].strip()
        next_blank = i + 1 >= len(lines) or not lines[i + 1].strip()
        if prev_blank and next_blank:
            found.append((i, start, line))

    return _merge_adjacent_headings(found, lines)


def _merge_adjacent_headings(
    found: List[Tuple[int, int, str]],
    lines: List[str],
) -> List[Tuple[int, str]]:
    """
    Join a heading to the one directly below it when no body text separates them.

    Legal texts routinely split a heading across two blocks — EUR-Lex renders GDPR as
    ``Article 9`` then ``Processing of special categories of personal data``. Kept apart,
    a chunk cites the least useful of the two; merged, it cites
    ``Article 9 — Processing of special categories of personal data``.
    """
    merged: List[Tuple[int, str]] = []
    idx = 0
    while idx < len(found):
        line_no, start, text = found[idx]
        parts = [text]
        # Cap at two: the pattern is "designation + title". Merging further starts
        # swallowing lead-in sentences, e.g. "Article 4 — Definitions — For the
        # purposes of this Regulation:".
        if idx + 1 < len(found):
            next_line, _, next_text = found[idx + 1]
            between = lines[line_no + 1 : next_line]
            if between and all(not b.strip() for b in between):
                parts.append(next_text)
                idx += 1
        merged.append((start, " — ".join(parts)))
        idx += 1
    return merged


def is_hard_wrapped(lines: List[str], *, min_lines: int = 6) -> bool:
    """
    True when the text is laid out at a fixed column width rather than in paragraphs.

    ``pypdf`` emits one line per *visual* line, so body text arrives hard-wrapped and often
    blank-line separated — which defeats a "standalone line" heading rule. In paragraph
    text, long lines end at sentence boundaries; in wrapped text, they break mid-clause.
    """
    body = [ln.strip() for ln in lines if ln.strip()]
    if len(body) < min_lines:
        return False
    long_lines = [ln for ln in body if len(ln) > 55]
    if len(long_lines) < min_lines // 2:
        return False
    unterminated = sum(1 for ln in long_lines if ln[-1] not in ".!?:;")
    return unterminated / len(long_lines) > 0.5


def _looks_like_heading(line: str) -> bool:
    if not (3 <= len(line) <= MAX_HEADING_CHARS):
        return False
    if line[-1] in ".,;":
        return False
    if "|" in line or _KEY_VALUE_LINE.match(line):
        return False
    if line[0] in _LIST_MARKERS:
        return False
    if not re.search(r"[A-Za-z]", line):
        return False
    # Headings start a phrase; wrapped prose usually resumes mid-sentence.
    if not (line[0].isupper() or line[0].isdigit()):
        return False
    # More than one sentence means it is prose, not a heading.
    if _SENTENCE_BOUNDARY.search(line):
        return False
    if line.count("(") != line.count(")"):
        return False
    words = re.findall(r"[A-Za-z']+", line)
    if not (1 <= len(words) <= 14):
        return False
    if words[-1].lower() in _CONTINUATION_WORDS:
        return False
    if _is_page_furniture(line):
        return False
    return True


def section_for_offset(headings: List[Tuple[int, str]], offset: int) -> Optional[str]:
    """Nearest heading at or before ``offset`` — the section a chunk starts inside."""
    found: Optional[str] = None
    for start, heading in headings:
        if start <= offset:
            found = heading
        else:
            break
    return found


def sections_for_span(
    headings: List[Tuple[int, str]],
    start: int,
    end: int,
) -> List[str]:
    """
    Every heading the span ``[start, end)`` sits under or runs into.

    A fixed-width chunk regularly straddles a boundary: a 900-character window opened
    inside GDPR Article 8 and closed inside Article 9. Labelling it from the start offset
    alone reports "Article 8" for text that is Article 9 — precisely the wrong-label
    failure this metadata exists to avoid. Returning both keeps the label truthful, and
    a reviewer can see the chunk spans a boundary.
    """
    covering = section_for_offset(headings, start)
    spanned = [h for pos, h in headings if start < pos < end]
    out: List[str] = []
    for heading in ([covering] if covering else []) + spanned:
        if heading and heading not in out:
            out.append(heading)
    return out
