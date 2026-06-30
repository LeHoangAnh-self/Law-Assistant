from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup, Tag


ARTICLE_RE = re.compile(r"^\s*[“\"]?Điều\s+([0-9]+[a-zA-Z]?)\.?\s*(.*)$", re.IGNORECASE)
ROMAN_SECTION_RE = re.compile(r"^\s*([IVXLCDM]+)\.\s+(.+)$", re.IGNORECASE)
CLAUSE_RE = re.compile(r"^\s*([0-9]+)\.\s+(.+)$")
POINT_RE = re.compile(r"^\s*([a-zđ])\)\s+(.+)$", re.IGNORECASE)
ANNEX_RE = re.compile(r"^\s*(Phụ\s+lục|PHỤ\s+LỤC)\b\s*(.*)$")
FORM_RE = re.compile(r"^\s*(Mẫu\s+số|MẪU\s+SỐ)\b\s*(.*)$")
INLINE_CLAUSE_RE = re.compile(r"\s([0-9]+)\.\s+")
INLINE_LEGAL_UNIT_RE = re.compile(r"(?:^|\s)([0-9]+\.|[a-zđ]\))\s+", re.IGNORECASE)
DOCUMENT_TITLE_RE = re.compile(
    r"^\s*(LUẬT|BỘ\s+LUẬT|NGHỊ\s+ĐỊNH|NGHỊ\s+QUYẾT|QUYẾT\s+ĐỊNH|THÔNG\s+TƯ|PHÁP\s+LỆNH)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ParsedPoint:
    label: str
    occurrence_index: int
    stable_anchor: str
    order_index: int
    content_text: str
    content_html: str | None = None


@dataclass(frozen=True)
class ParsedClause:
    number: str
    occurrence_index: int
    stable_anchor: str
    order_index: int
    content_text: str
    content_html: str | None = None
    points: list[ParsedPoint] = field(default_factory=list)


@dataclass(frozen=True)
class ParsedArticle:
    number: str
    occurrence_index: int
    title: str | None
    stable_anchor: str
    order_index: int
    content_text: str
    content_html: str | None
    clauses: list[ParsedClause] = field(default_factory=list)


@dataclass(frozen=True)
class ParsedTable:
    stable_anchor: str
    order_index: int
    caption: str | None
    html: str
    text: str
    article_anchor: str | None


@dataclass(frozen=True)
class ParsedAttachment:
    stable_anchor: str
    title: str | None
    source_url: str | None
    html: str | None
    text: str | None


@dataclass(frozen=True)
class ParsedAnnex:
    stable_anchor: str
    title: str | None
    order_index: int
    html: str | None
    text: str | None


@dataclass(frozen=True)
class ParsedDocument:
    content_html: str
    content_text: str
    source_hash: str
    title: str | None
    articles: list[ParsedArticle]
    tables: list[ParsedTable]
    forms: list[ParsedAttachment]
    annexes: list[ParsedAnnex]


def parse_document_html(html: str) -> ParsedDocument:
    soup = BeautifulSoup(html, "html.parser")
    root = soup.find(id="toanvancontent") or soup.find("div", class_="fulltext") or soup
    content_html = str(root)
    content_text = _clean_text(root.get_text("\n"))
    title = _extract_title(soup, root)

    blocks = _content_blocks(root)
    articles, tables, annexes = _parse_blocks(blocks)
    forms = _parse_forms(root)

    return ParsedDocument(
        content_html=content_html,
        content_text=content_text,
        source_hash=hashlib.sha256(content_html.encode("utf-8")).hexdigest(),
        title=title,
        articles=articles,
        tables=tables,
        forms=forms,
        annexes=annexes,
    )


def _extract_title(soup: BeautifulSoup, root: Tag | BeautifulSoup) -> str | None:
    selectors = [
        "h1",
        "h2",
        ".title",
        ".vb-title",
        ".doc-title",
    ]
    for selector in selectors:
        element = soup.select_one(selector)
        if element:
            text = _clean_text(element.get_text(" "))
            if text:
                return text[:1500]

    first_bold = root.find(["b", "strong"]) if isinstance(root, Tag) else None
    if first_bold:
        text = _clean_text(first_bold.get_text(" "))
        if text and not ARTICLE_RE.match(text):
            return text[:1500]

    for block in _content_blocks(root):
        text = _clean_text(block.get_text(" "))
        if DOCUMENT_TITLE_RE.match(text):
            return text[:1500]
    return None


def _content_blocks(root: Tag | BeautifulSoup) -> list[Tag]:
    candidates = root.find_all(["p", "table", "div"], recursive=True)
    blocks: list[Tag] = []
    seen: set[int] = set()
    for tag in candidates:
        if id(tag) in seen:
            continue
        seen.add(id(tag))
        if tag.name == "div" and tag.find(["p", "table"]):
            continue
        text = _clean_text(tag.get_text(" "))
        if tag.name == "table" or text:
            blocks.append(tag)
    return blocks


def _parse_blocks(blocks: list[Tag]) -> tuple[list[ParsedArticle], list[ParsedTable], list[ParsedAnnex]]:
    article_builders: list[_ArticleBuilder] = []
    current_article: _ArticleBuilder | None = None
    current_clause: _ClauseBuilder | None = None
    current_annex: _AnnexBuilder | None = None
    article_counts: dict[str, int] = {}
    roman_section_mode = False
    tables: list[ParsedTable] = []
    annex_builders: list[_AnnexBuilder] = []

    for block in blocks:
        if block.name == "table":
            table_index = len(tables) + 1
            article_anchor = current_article.stable_anchor if current_article else None
            tables.append(
                ParsedTable(
                    stable_anchor=_anchor("table", table_index),
                    order_index=table_index,
                    caption=_table_caption(block),
                    html=str(block),
                    text=_clean_text(block.get_text(" | ")),
                    article_anchor=article_anchor,
                )
            )
            if current_article:
                current_article.html_parts.append(str(block))
            if current_annex:
                current_annex.add_block(_clean_text(block.get_text(" | ")), str(block))
            continue

        text = _clean_text(block.get_text(" "))
        if not text:
            continue

        article_match = ARTICLE_RE.match(text)
        if article_match and current_annex is None:
            number = article_match.group(1)
            article_counts[number] = article_counts.get(number, 0) + 1
            occurrence_index = article_counts[number]
            title, tail = _split_article_title_tail(article_match.group(2).strip())
            current_article = _ArticleBuilder(
                number=number,
                occurrence_index=occurrence_index,
                title=_limit_text(title, 1000) if title else None,
                stable_anchor=_article_anchor(number, occurrence_index),
                order_index=len(article_builders) + 1,
            )
            current_article.add_block(_article_heading_text(number, title), str(block))
            article_builders.append(current_article)
            current_clause = None
            if tail:
                current_clause = _parse_inline_article_tail(
                    tail,
                    str(block),
                    current_article=current_article,
                    current_clause=current_clause,
                )
            continue

        roman_match = ROMAN_SECTION_RE.match(text)
        if roman_match and current_annex is None and (roman_section_mode or not article_builders):
            roman_section_mode = True
            number = roman_match.group(1).upper()
            article_counts[number] = article_counts.get(number, 0) + 1
            occurrence_index = article_counts[number]
            title, tail = _split_article_title_tail(roman_match.group(2).strip())
            current_article = _ArticleBuilder(
                number=number,
                occurrence_index=occurrence_index,
                title=_limit_text(title, 1000) if title else None,
                stable_anchor=_article_anchor(number, occurrence_index),
                order_index=len(article_builders) + 1,
            )
            current_article.add_block(_roman_section_heading_text(number, title), str(block))
            article_builders.append(current_article)
            current_clause = None
            if tail:
                current_clause = _parse_inline_article_tail(
                    tail,
                    str(block),
                    current_article=current_article,
                    current_clause=current_clause,
                )
            continue

        annex_match = ANNEX_RE.match(text)
        if annex_match:
            current_annex = _AnnexBuilder(
                stable_anchor=_anchor("annex", len(annex_builders) + 1),
                title=text[:1000],
                order_index=len(annex_builders) + 1,
            )
            current_annex.add_block(text, str(block))
            annex_builders.append(current_annex)
            current_article = None
            current_clause = None
            continue

        if current_annex:
            current_annex.add_block(text, str(block))
            continue

        if not current_article:
            continue

        clause_match = CLAUSE_RE.match(text)
        if clause_match:
            clause_number = clause_match.group(1)
            occurrence_index = current_article.next_clause_occurrence(clause_number)
            current_clause = _ClauseBuilder(
                number=clause_number,
                occurrence_index=occurrence_index,
                stable_anchor=_clause_anchor(current_article.stable_anchor, clause_number, occurrence_index),
                order_index=len(current_article.clauses) + 1,
            )
            current_clause.add_block(text, str(block))
            current_article.clauses.append(current_clause)
            current_article.add_block(text, str(block))
            continue

        point_match = POINT_RE.match(text)
        if point_match and current_clause:
            label = point_match.group(1).lower()
            occurrence_index = current_clause.next_point_occurrence(label)
            current_clause.points.append(
                ParsedPoint(
                    label=label,
                    occurrence_index=occurrence_index,
                    stable_anchor=_point_anchor(current_clause.stable_anchor, label, occurrence_index),
                    order_index=len(current_clause.points) + 1,
                    content_text=text,
                    content_html=str(block),
                )
            )
            current_clause.add_block(text, str(block))
            current_article.add_block(text, str(block))
            continue

        if current_clause:
            current_clause.add_block(text, str(block))
        current_article.add_block(text, str(block))

    return ([builder.build() for builder in article_builders], tables, [builder.build() for builder in annex_builders])


def _split_article_title_tail(text: str) -> tuple[str | None, str | None]:
    if not text:
        return None, None
    match = INLINE_CLAUSE_RE.search(text)
    if not match:
        return text, None
    title = text[: match.start()].strip()
    tail = text[match.start(1) :].strip()
    return title or None, tail or None


def _article_heading_text(number: str, title: str | None) -> str:
    if title:
        return f"Điều {number}. {title}"
    return f"Điều {number}."


def _roman_section_heading_text(number: str, title: str | None) -> str:
    if title:
        return f"{number}. {title}"
    return f"{number}."


def _parse_inline_article_tail(
    text: str,
    html: str,
    *,
    current_article: "_ArticleBuilder",
    current_clause: "_ClauseBuilder | None",
) -> "_ClauseBuilder | None":
    for unit in _split_inline_legal_units(text):
        clause_match = CLAUSE_RE.match(unit)
        if clause_match:
            clause_number = clause_match.group(1)
            occurrence_index = current_article.next_clause_occurrence(clause_number)
            current_clause = _ClauseBuilder(
                number=clause_number,
                occurrence_index=occurrence_index,
                stable_anchor=_clause_anchor(current_article.stable_anchor, clause_number, occurrence_index),
                order_index=len(current_article.clauses) + 1,
            )
            current_clause.add_block(unit, html)
            current_article.clauses.append(current_clause)
            current_article.add_block(unit, html)
            continue

        point_match = POINT_RE.match(unit)
        if point_match and current_clause:
            label = point_match.group(1).lower()
            occurrence_index = current_clause.next_point_occurrence(label)
            current_clause.points.append(
                ParsedPoint(
                    label=label,
                    occurrence_index=occurrence_index,
                    stable_anchor=_point_anchor(current_clause.stable_anchor, label, occurrence_index),
                    order_index=len(current_clause.points) + 1,
                    content_text=unit,
                    content_html=html,
                )
            )
            current_clause.add_block(unit, html)
            current_article.add_block(unit, html)
            continue

        if current_clause:
            current_clause.add_block(unit, html)
        current_article.add_block(unit, html)
    return current_clause


def _split_inline_legal_units(text: str) -> list[str]:
    matches = list(INLINE_LEGAL_UNIT_RE.finditer(text))
    if not matches:
        return [text] if text else []

    units: list[str] = []
    if matches[0].start(1) > 0:
        prefix = text[: matches[0].start(1)].strip()
        if prefix:
            units.append(prefix)

    for index, match in enumerate(matches):
        start = match.start(1)
        end = matches[index + 1].start(1) if index + 1 < len(matches) else len(text)
        unit = text[start:end].strip()
        if unit:
            units.append(unit)
    return units


def _parse_forms(root: Tag | BeautifulSoup) -> list[ParsedAttachment]:
    forms: list[ParsedAttachment] = []
    for link in root.find_all("a"):
        text = _clean_text(link.get_text(" "))
        href = link.get("href")
        if not text and not href:
            continue
        if FORM_RE.match(text) or (href and "mau" in href.lower()):
            forms.append(
                ParsedAttachment(
                    stable_anchor=_anchor("form", len(forms) + 1),
                    title=text[:1000] if text else None,
                    source_url=href,
                    html=str(link),
                    text=text or None,
                )
            )
    return forms


def _table_caption(table: Tag) -> str | None:
    caption = table.find("caption")
    if caption:
        text = _clean_text(caption.get_text(" "))
        return text[:1000] if text else None
    previous = table.find_previous(["p", "div"])
    if previous:
        text = _clean_text(previous.get_text(" "))
        if text.lower().startswith(("bảng", "biểu")):
            return text[:1000]
    return None


def _anchor(prefix: str, value: int | str) -> str:
    normalized = str(value).strip().lower().replace(" ", "-")
    return f"{prefix}-{normalized}"


def _article_anchor(article_number: str, occurrence_index: int) -> str:
    suffix = "" if occurrence_index == 1 else f".occurrence-{occurrence_index}"
    return f"{_anchor('article', article_number)}{suffix}"


def _clause_anchor(article_anchor: str, clause_number: str, occurrence_index: int) -> str:
    suffix = "" if occurrence_index == 1 else f".occurrence-{occurrence_index}"
    return f"{article_anchor}.clause-{clause_number}{suffix}"


def _point_anchor(clause_anchor: str, point_label: str, occurrence_index: int) -> str:
    suffix = "" if occurrence_index == 1 else f".occurrence-{occurrence_index}"
    return f"{clause_anchor}.point-{point_label}{suffix}"


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _limit_text(text: str, max_length: int) -> str:
    return text[:max_length]


@dataclass
class _ClauseBuilder:
    number: str
    occurrence_index: int
    stable_anchor: str
    order_index: int
    text_parts: list[str] = field(default_factory=list)
    html_parts: list[str] = field(default_factory=list)
    points: list[ParsedPoint] = field(default_factory=list)
    point_counts: dict[str, int] = field(default_factory=dict)

    def add_block(self, text: str, html: str) -> None:
        self.text_parts.append(text)
        self.html_parts.append(html)

    def next_point_occurrence(self, label: str) -> int:
        self.point_counts[label] = self.point_counts.get(label, 0) + 1
        return self.point_counts[label]

    def build(self) -> ParsedClause:
        return ParsedClause(
            number=self.number,
            occurrence_index=self.occurrence_index,
            stable_anchor=self.stable_anchor,
            order_index=self.order_index,
            content_text="\n".join(self.text_parts),
            content_html="\n".join(self.html_parts),
            points=self.points,
        )


@dataclass
class _ArticleBuilder:
    number: str
    occurrence_index: int
    title: str | None
    stable_anchor: str
    order_index: int
    text_parts: list[str] = field(default_factory=list)
    html_parts: list[str] = field(default_factory=list)
    clauses: list[_ClauseBuilder] = field(default_factory=list)
    clause_counts: dict[str, int] = field(default_factory=dict)

    def add_block(self, text: str, html: str) -> None:
        self.text_parts.append(text)
        self.html_parts.append(html)

    def next_clause_occurrence(self, number: str) -> int:
        self.clause_counts[number] = self.clause_counts.get(number, 0) + 1
        return self.clause_counts[number]

    def build(self) -> ParsedArticle:
        return ParsedArticle(
            number=self.number,
            occurrence_index=self.occurrence_index,
            title=self.title,
            stable_anchor=self.stable_anchor,
            order_index=self.order_index,
            content_text="\n".join(self.text_parts),
            content_html="\n".join(self.html_parts),
            clauses=[clause.build() for clause in self.clauses],
        )


@dataclass
class _AnnexBuilder:
    stable_anchor: str
    title: str | None
    order_index: int
    text_parts: list[str] = field(default_factory=list)
    html_parts: list[str] = field(default_factory=list)

    def add_block(self, text: str, html: str) -> None:
        self.text_parts.append(text)
        self.html_parts.append(html)

    def build(self) -> ParsedAnnex:
        return ParsedAnnex(
            stable_anchor=self.stable_anchor,
            title=self.title,
            order_index=self.order_index,
            html="\n".join(self.html_parts),
            text="\n".join(self.text_parts),
        )
