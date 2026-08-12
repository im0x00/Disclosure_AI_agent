"""A byte-span tokenizer for malformed DART markup and HTML.

The tokenizer never decodes and re-encodes source content. Every token points to
the original byte buffer, and token spans form an exact partition of that buffer.
"""

from __future__ import annotations

from disclosure_ai.data.models import AttributeSpan, SourceFormat, Token, TokenKind

_SPACE = b" \t\r\n\f"
_NAME_EXTRA = b"_-:."


def tokenize(source: bytes, source_format: SourceFormat) -> tuple[Token, ...]:
    if source_format not in {SourceFormat.DART_MARKUP, SourceFormat.HTML}:
        return (Token(TokenKind.RAW, 0, len(source)),) if source else ()

    html_mode = source_format is SourceFormat.HTML
    tokens: list[Token] = []
    text_start = 0
    search_from = 0
    size = len(source)

    while search_from < size:
        start = source.find(b"<", search_from)
        if start < 0:
            break
        token = _token_at(source, start, html_mode=html_mode)
        if token is None:
            search_from = start + 1
            continue
        if text_start < start:
            tokens.append(Token(TokenKind.TEXT, text_start, start))
        tokens.append(token)
        text_start = token.end_byte
        search_from = token.end_byte

    if text_start < size:
        tokens.append(Token(TokenKind.TEXT, text_start, size))
    return tuple(tokens)


def _token_at(source: bytes, start: int, *, html_mode: bool) -> Token | None:
    tail = source[start : start + 16].lower()
    if source.startswith(b"<!--", start):
        end_marker = source.find(b"-->", start + 4)
        if end_marker < 0:
            return Token(
                TokenKind.COMMENT,
                start,
                len(source),
                issues=("unterminated-comment",),
            )
        return Token(TokenKind.COMMENT, start, end_marker + 3)

    if source.startswith(b"<![CDATA[", start):
        end_marker = source.find(b"]]>", start + 9)
        if end_marker < 0:
            return Token(
                TokenKind.CDATA,
                start,
                len(source),
                issues=("unterminated-cdata",),
            )
        return Token(TokenKind.CDATA, start, end_marker + 3)

    if source.startswith(b"<?", start):
        end_marker = source.find(b"?>", start + 2)
        issues: tuple[str, ...] = ()
        if end_marker < 0:
            end_marker = _find_tag_end(source, start + 2)
            if end_marker < 0:
                return None
            end = end_marker + 1
            issues = ("processing-instruction-ended-by-angle-bracket",)
        else:
            end = end_marker + 2
        name_start = start + 2
        name_end = _scan_name(source, name_start)
        name = _decode_name(source[name_start:name_end]) if name_end > name_start else None
        kind = (
            TokenKind.XML_DECLARATION
            if name and name.lower() == "xml"
            else TokenKind.PROCESSING_INSTRUCTION
        )
        return Token(kind, start, end, name=name, issues=issues)

    if tail.startswith(b"<!doctype"):
        end_marker = _find_declaration_end(source, start + 2)
        if end_marker < 0:
            return Token(
                TokenKind.DOCTYPE,
                start,
                len(source),
                issues=("unterminated-doctype",),
            )
        return Token(TokenKind.DOCTYPE, start, end_marker + 1, name="DOCTYPE")

    is_end = source.startswith(b"</", start)
    name_start = start + (2 if is_end else 1)
    if name_start >= len(source) or not _valid_name_start(source[name_start], html_mode):
        return None
    name_end = _scan_name(source, name_start)
    if name_end >= len(source) or source[name_end] not in _SPACE + b"/>":
        return None
    end_marker = _find_tag_end(source, name_end)
    if end_marker < 0:
        return None
    name = _decode_name(source[name_start:name_end])
    if is_end:
        return Token(TokenKind.END_TAG, start, end_marker + 1, name=name)

    slash = end_marker - 1
    while slash > name_end and source[slash] in _SPACE:
        slash -= 1
    kind = TokenKind.SELF_CLOSING_TAG if source[slash : slash + 1] == b"/" else TokenKind.START_TAG
    attributes, issues = _parse_attributes(source, name_end, end_marker)
    return Token(
        kind,
        start,
        end_marker + 1,
        name=name,
        attributes=attributes,
        issues=issues,
    )


def _valid_name_start(value: int, html_mode: bool) -> bool:
    if html_mode:
        return 65 <= value <= 90 or 97 <= value <= 122
    return 65 <= value <= 90


def _scan_name(source: bytes, start: int) -> int:
    cursor = start
    while cursor < len(source):
        value = source[cursor]
        if not (
            48 <= value <= 57 or 65 <= value <= 90 or 97 <= value <= 122 or value in _NAME_EXTRA
        ):
            break
        cursor += 1
    return cursor


def _find_tag_end(source: bytes, start: int) -> int:
    quote: int | None = None
    cursor = start
    while cursor < len(source):
        value = source[cursor]
        if quote is not None:
            if value == quote:
                quote = None
        elif value in (34, 39):
            quote = value
        elif value == 62:
            return cursor
        cursor += 1
    return -1


def _find_declaration_end(source: bytes, start: int) -> int:
    quote: int | None = None
    bracket_depth = 0
    cursor = start
    while cursor < len(source):
        value = source[cursor]
        if quote is not None:
            if value == quote:
                quote = None
        elif value in (34, 39):
            quote = value
        elif value == 91:
            bracket_depth += 1
        elif value == 93 and bracket_depth:
            bracket_depth -= 1
        elif value == 62 and bracket_depth == 0:
            return cursor
        cursor += 1
    return -1


def _parse_attributes(
    source: bytes, start: int, end_marker: int
) -> tuple[tuple[AttributeSpan, ...], tuple[str, ...]]:
    attributes: list[AttributeSpan] = []
    issues: list[str] = []
    cursor = start
    while cursor < end_marker:
        while cursor < end_marker and source[cursor] in _SPACE:
            cursor += 1
        if cursor >= end_marker or source[cursor] == 47:
            break
        attr_start = cursor
        while cursor < end_marker and source[cursor] not in _SPACE + b"=<>/":
            cursor += 1
        name_end = cursor
        if name_end == attr_start:
            issues.append(f"unparsed-attribute-byte:{cursor}")
            cursor += 1
            continue
        while cursor < end_marker and source[cursor] in _SPACE:
            cursor += 1

        value: str | None = None
        quote: str | None = None
        value_start: int | None = None
        value_end: int | None = None
        if cursor < end_marker and source[cursor] == 61:
            cursor += 1
            while cursor < end_marker and source[cursor] in _SPACE:
                cursor += 1
            if cursor < end_marker and source[cursor] in (34, 39):
                quote_byte = source[cursor]
                quote = chr(quote_byte)
                cursor += 1
                value_start = cursor
                while cursor < end_marker and source[cursor] != quote_byte:
                    cursor += 1
                value_end = cursor
                value = source[value_start:value_end].decode("utf-8", errors="replace")
                if cursor < end_marker:
                    cursor += 1
                else:
                    issues.append(f"unterminated-attribute-quote:{attr_start}")
            else:
                value_start = cursor
                while cursor < end_marker and source[cursor] not in _SPACE + b">":
                    cursor += 1
                value_end = cursor
                value = source[value_start:value_end].decode("utf-8", errors="replace")
        attributes.append(
            AttributeSpan(
                name=source[attr_start:name_end].decode("utf-8", errors="replace"),
                value=value,
                quote=quote,
                start_byte=attr_start,
                end_byte=cursor,
                name_start_byte=attr_start,
                name_end_byte=name_end,
                value_start_byte=value_start,
                value_end_byte=value_end,
            )
        )
    return tuple(attributes), tuple(issues)


def _decode_name(value: bytes) -> str:
    return value.decode("ascii", errors="replace")
