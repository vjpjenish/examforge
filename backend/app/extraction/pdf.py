"""PDF access: page slicing, native text layer, and figure cropping (PyMuPDF).

Pages go to the model as one-page PDFs, not as rasterised images: the model runs its own layout and
OCR pass over the original vectors, which reads multi-column papers and option grids far better than
our text layer ever did. PyMuPDF is used only to cut pages out, to crop figures, and to read the text
layer for the few places that need exact characters.

The text layer is NOT sent to the model any more. It is rebuilt in reading order here because two
things still need it: the strict parse of answer-key grids printed in the paper (`keys.py`), where
exact characters beat a model reading, and `HeuristicProvider`, the offline no-API-key mode.
Fragments are joined into lines by baseline, two-column pages are read left column then right column
(full-width lines such as headings split the page into bands), and running headers/footers that repeat
across pages are removed. PyMuPDF's own `sort=True` interleaves the two columns line by line, which
garbles questions.
"""

import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf


@dataclass
class PageContent:
    index: int  # 0-based page index in the document
    pdf: bytes  # this single page as a standalone one-page PDF, as sent to the model
    text: str  # native text layer; empty for scanned pages. Never sent to the model; see module docstring.
    width: float
    height: float
    removed: list[str] = field(default_factory=list)  # running headers/footers stripped from `text`
    # Share of the page's dark ink that the text layer accounts for. Low on scans and on PDFs whose
    # fonts have no Unicode mapping: the page shows text that the text layer does not contain.
    text_coverage: float = 1.0
    # The same text in plain top-to-bottom rows across the full width (no column split). Tables such as
    # multi-column answer-key grids keep their rows here.
    rows: str = ""

    @property
    def is_scanned(self) -> bool:
        return len(self.text.strip()) < 40

    @property
    def text_incomplete(self) -> bool:
        return self.is_scanned or self.text_coverage < 0.75


def page_count(path: str | Path) -> int:
    with pymupdf.open(path) as doc:
        return doc.page_count


@dataclass
class _Frag:
    x0: float
    y0: float
    x1: float
    y1: float
    text: str


def _horizontal_lines(page: pymupdf.Page) -> list[dict]:
    """Text lines, minus rotated ones: diagonal or vertical text on exam pages is a watermark."""
    lines = [line for b in page.get_text("dict")["blocks"] for line in b.get("lines", [])]
    return [line for line in lines if abs(line["dir"][1]) < 0.05 and line["dir"][0] > 0]


def _fragments(page: pymupdf.Page) -> list[_Frag]:
    out = []
    for line in _horizontal_lines(page):
        text = "".join(span["text"] for span in line["spans"]).replace("\t", " ")
        if text.strip():
            x0, y0, x1, y1 = line["bbox"]
            out.append(_Frag(x0, y0, x1, y1, re.sub(r"\s+", " ", text).strip()))
    return out


def _table_markdown(table) -> str:
    """A detected table as a Markdown pipe table, or "" if it is not worth keeping.

    `to_markdown()` is not used: it labels an empty header cell "Col1" and joins wrapped
    cell text with a literal <br>, which the question renderer escapes and shows verbatim.
    """
    rows = [
        [(cell or "").replace("\n", " ").replace("|", "/").strip() for cell in row]
        for row in table.extract()
    ]
    rows = [r for r in rows if any(r)]
    if len(rows) < 2 or len(rows[0]) < 2:
        return ""
    head, *body = rows
    out = ["| " + " | ".join(head) + " |", "| " + " | ".join("---" for _ in head) + " |"]
    out += ["| " + " | ".join(r + [""] * (len(head) - len(r))) + " |" for r in body]
    return "\n".join(out)


def _tables(page: pymupdf.Page) -> list[tuple[pymupdf.Rect, str]]:
    """Ruled tables on the page, as Markdown.

    Only tables drawn with real lines count (`lines_strict`). Exam papers lay options and
    two-column text out on an invisible grid, and the looser strategies read those as tables,
    which would wreck ordinary questions. A paper's matching table is always ruled.
    """
    try:
        found = page.find_tables(strategy="lines_strict").tables
    except Exception:  # pragma: no cover - a malformed page must not fail the whole extraction
        return []
    out = []
    for table in found:
        if table.row_count < 2 or table.col_count < 2:
            continue
        if md := _table_markdown(table):
            out.append((pymupdf.Rect(table.bbox), md))
    return out


def _gutter(frags: list[_Frag], width: float) -> float | None:
    """x of the gap between two columns, or None for a single-column page."""
    if len(frags) < 8:
        return None
    lo, hi = int(width * 0.35), int(width * 0.65)
    best, best_x = None, None
    for x in range(lo, hi + 1, 2):
        crossing = sum(1 for f in frags if f.x0 < x - 1 and f.x1 > x + 1)
        if best is None or crossing < best:
            best, best_x = crossing, x
    left = sum(1 for f in frags if f.x1 <= best_x)
    right = sum(1 for f in frags if f.x0 >= best_x)
    # Real columns: both sides well populated and only full-width lines (headings, tables) cross the gap.
    if left >= 4 and right >= 4 and best <= 0.15 * len(frags):
        return float(best_x)
    return None


def reading_order_lines(page: pymupdf.Page) -> list[tuple[str, float]]:
    """(line, vertical position 0-1) in reading order."""
    frags = _fragments(page)
    height = page.rect.height or 1
    # Swap each ruled table for one fragment holding its Markdown. Without this the table's
    # rows arrive as loose lines ("Supersonic Cruise" on its own) and the pairing is lost.
    for rect, md in _tables(page):
        frags = [f for f in frags if not (rect.x0 - 2 <= (f.x0 + f.x1) / 2 <= rect.x1 + 2 and rect.y0 - 2 <= (f.y0 + f.y1) / 2 <= rect.y1 + 2)]
        frags.append(_Frag(rect.x0, rect.y0, rect.x1, rect.y1, md))
    gutter = _gutter(frags, page.rect.width)
    if gutter is None:
        return _positioned(frags, height)
    spans = sorted((f for f in frags if f.x0 < gutter - 1 and f.x1 > gutter + 1), key=lambda f: f.y0)
    out: list[tuple[str, float]] = []
    top = -1.0
    # Full-width lines cut the page into bands; each band is read left column first.
    for cut in [*spans, None]:
        bottom = cut.y0 if cut else float("inf")
        band = [f for f in frags if top <= (f.y0 + f.y1) / 2 < bottom and f not in spans]
        out += _positioned([f for f in band if f.x1 <= gutter + 1], height)
        out += _positioned([f for f in band if f.x0 >= gutter - 1 and f.x1 > gutter + 1], height)
        if cut is not None:
            out += _positioned([cut], height)
            top = (cut.y0 + cut.y1) / 2 + 0.01
    return out


def _positioned(frags: list[_Frag], height: float) -> list[tuple[str, float]]:
    rows: list[list[_Frag]] = []
    for f in sorted(frags, key=lambda f: (f.y0 + f.y1) / 2):
        mid = (f.y0 + f.y1) / 2
        if rows:
            last = rows[-1]
            ref = sum((g.y0 + g.y1) / 2 for g in last) / len(last)
            if abs(mid - ref) <= max(2.5, 0.35 * (f.y1 - f.y0)):
                last.append(f)
                continue
        rows.append([f])
    return [
        (" ".join(g.text for g in sorted(row, key=lambda g: g.x0)), min(g.y0 for g in row) / height) for row in rows
    ]


# Lines that carry question content are never stripped, even when they repeat at the same spot on many
# pages ("(d) 1, 2 and 3" ends a lot of pages in a UPSC paper). Keeping a stray footer is harmless; the
# model is told to ignore it. Losing an option is not.
_CONTENT_LINE = re.compile(
    r"^\s*(?:(?:Q(?:ues(?:tion)?)?\s*[.:]?\s*(?:No\.?)?\s*)?\d{1,3}\s*[.):]|\(?[a-hA-H]\s*[.)]|\(?(?:i{1,3}|iv|v|vi{0,3})\s*[.)])"
)
_MARGIN_TOP, _MARGIN_BOTTOM = 0.09, 0.88


def _ink_boxes(page: pymupdf.Page) -> list[tuple[float, float, float, float]]:
    """Boxes of everything on the page that is not missing text: text lines, images, vector graphics."""
    boxes = [tuple(line["bbox"]) for line in _horizontal_lines(page)]
    area = page.rect.width * page.rect.height
    for info in page.get_image_info():
        x0, y0, x1, y1 = info["bbox"]
        # Figures (even large maps) are not missing text. A page-sized image is a scan: its ink only
        # counts as covered where the text layer overlaps it.
        if (x1 - x0) * (y1 - y0) < 0.85 * area:
            boxes.append((x0, y0, x1, y1))
    for path in page.get_drawings():
        fill = path.get("fill")
        filled = fill is not None
        # A dark filled shape (heading bar, table header) is decoration ink, not hidden text.
        dark_fill = filled and sum(fill) / max(1, len(fill)) < 0.45
        for item in path["items"]:
            if item[0] in ("re", "qu"):
                r = item[1] if item[0] == "re" else item[1].rect
                # Small filled shapes (bullets, glyph-like marks) are ink. Large ones are backgrounds or
                # boxes drawn behind text, so only their edges count; otherwise they would hide missing text.
                if filled and (r.width * r.height < 0.01 * area or dark_fill):
                    boxes.append((r.x0, r.y0, r.x1, r.y1))
                else:
                    boxes += [(r.x0, r.y0, r.x1, r.y0), (r.x0, r.y1, r.x1, r.y1), (r.x0, r.y0, r.x0, r.y1), (r.x1, r.y0, r.x1, r.y1)]
                continue
            pts = [v for v in item[1:] if isinstance(v, pymupdf.Point)]
            if pts:
                x0, y0 = min(p.x for p in pts), min(p.y for p in pts)
                x1, y1 = max(p.x for p in pts), max(p.y for p in pts)
                if (x1 - x0) * (y1 - y0) < 0.01 * area or min(x1 - x0, y1 - y0) < 3:
                    boxes.append((x0, y0, x1, y1))
    return boxes


def text_coverage(page: pymupdf.Page) -> float:
    """Fraction of the page's dark ink explained by the text layer, images and vector graphics.

    Light watermarks are ignored. A page full of drawing paths is treated as outlined text (no coverage)."""
    if len(page.get_drawings()) > 1500:
        return 0.0
    dpi = 60
    pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY)
    scale = dpi / 72
    covered = bytearray(pix.width * pix.height)
    for x0, y0, x1, y1 in _ink_boxes(page):
        c0, c1 = max(0, int(x0 * scale) - 1), min(pix.width, int(x1 * scale) + 2)
        if c1 <= c0:
            continue
        for row in range(max(0, int(y0 * scale) - 1), min(pix.height, int(y1 * scale) + 2)):
            covered[row * pix.width + c0 : row * pix.width + c1] = bytes([1]) * (c1 - c0)
    samples = pix.samples
    dark = [i for i in range(len(samples)) if samples[i] < 110]
    if len(dark) < 200:
        return 1.0
    return sum(covered[i] for i in dark) / len(dark)


def _boilerplate_key(line: str, y: float) -> str:
    if _CONTENT_LINE.match(line):
        return ""
    key = re.sub(r"\s+", " ", line).strip().casefold()
    # Page numbers vary per page ("38 www.visionias.in"), so digits are masked. Question and option lines
    # never get here, and the line must also sit at the same height on many pages.
    key = re.sub(r"\d+", "#", key)
    # Running headers/footers sit at the same height on every page.
    return f"{round(y * 100)}|{key}" if key.strip("# ") else ""


def _in_margin(y: float) -> bool:
    return y < _MARGIN_TOP or y > _MARGIN_BOTTOM


def _running_lines(pages: list[list[tuple[str, float]]]) -> set[str]:
    """Lines in the top/bottom margin that repeat on many pages: headers, footers, page numbers, URLs."""
    if len(pages) < 2:
        return set()
    counts: Counter[str] = Counter()
    for lines in pages:
        counts.update({_boilerplate_key(t, y) for t, y in lines if _in_margin(y)} - {""})
    need = 2 if len(pages) == 2 else max(3, int(0.4 * len(pages)))
    return {k for k, n in counts.items() if n >= need}


def one_page_pdf(doc: pymupdf.Document, page_index: int) -> bytes:
    """One page of `doc` as a standalone single-page PDF.

    Vectors, fonts and embedded images are copied as they are, so the model sees the page at full
    fidelity instead of a flattened raster. Annotations are dropped: highlights and sticky notes left
    in a downloaded paper are not part of the printed question."""
    with pymupdf.open() as out:
        out.insert_pdf(doc, from_page=page_index, to_page=page_index, annots=False)
        return out.tobytes(garbage=3, deflate=True)


def load_pages(path: str | Path) -> list[PageContent]:
    """Every page as a one-page PDF, plus its text layer for the key parser and heuristic mode."""
    pages: list[PageContent] = []
    with pymupdf.open(path) as doc:
        ordered = [reading_order_lines(page) for page in doc]
        running = _running_lines(ordered)
        for page, lines in zip(doc, ordered):
            kept, removed = [], []
            for text, y in lines:
                strip = _in_margin(y) and _boilerplate_key(text, y) in running
                (removed if strip else kept).append(text)
            pages.append(
                PageContent(
                    index=page.number,
                    pdf=one_page_pdf(doc, page.number),
                    text="\n".join(kept),
                    width=page.rect.width,
                    height=page.rect.height,
                    removed=removed,
                    text_coverage=round(text_coverage(page), 3),
                    rows="\n".join(t for t, _ in _positioned(_fragments(page), page.rect.height or 1)),
                )
            )
    return pages


def crop_figure(path: str | Path, page_index: int, box_2d: list[int], out_path: Path, dpi: int = 220) -> bool:
    """Crop a [ymin, xmin, ymax, xmax] (0-1000) region of a page into a PNG."""
    if len(box_2d) != 4:
        return False
    ymin, xmin, ymax, xmax = (max(0, min(1000, v)) for v in box_2d)
    if ymax - ymin < 5 or xmax - xmin < 5:
        return False
    with pymupdf.open(path) as doc:
        if not 0 <= page_index < doc.page_count:
            return False
        page = doc[page_index]
        r = page.rect
        pad = 6  # points; boxes from vision models are often a hair tight
        clip = pymupdf.Rect(
            r.x0 + r.width * xmin / 1000 - pad,
            r.y0 + r.height * ymin / 1000 - pad,
            r.x0 + r.width * xmax / 1000 + pad,
            r.y0 + r.height * ymax / 1000 + pad,
        ) & r
        out_path.parent.mkdir(parents=True, exist_ok=True)
        page.get_pixmap(dpi=dpi, clip=clip).save(out_path)
    return True
