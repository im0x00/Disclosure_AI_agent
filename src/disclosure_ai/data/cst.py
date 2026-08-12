"""Recovery-aware concrete syntax tree built over lossless tokens."""

from __future__ import annotations

from dataclasses import dataclass, field

from disclosure_ai.data.models import (
    CstNode,
    NodeKind,
    RecoveryEvent,
    SourceFormat,
    Token,
    TokenKind,
)

_HTML_VOID = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}

_HTML_CLOSE_ON_START: dict[str, set[str]] = {
    "li": {"li"},
    "option": {"option"},
    "p": {"p"},
    "td": {"td", "th"},
    "th": {"td", "th"},
    "tr": {"td", "th", "tr"},
    "tbody": {"td", "th", "tr", "tbody", "thead", "tfoot"},
    "thead": {"td", "th", "tr", "tbody", "thead", "tfoot"},
    "tfoot": {"td", "th", "tr", "tbody", "thead", "tfoot"},
}


@dataclass(slots=True)
class _MutableNode:
    node_id: int
    kind: NodeKind
    parent_id: int | None
    children: list[int] = field(default_factory=list)
    name: str | None = None
    start_byte: int = 0
    end_byte: int = 0
    start_token_index: int | None = None
    end_token_index: int | None = None
    implicitly_closed: bool = False


def build_cst(
    tokens: tuple[Token, ...], source_size: int, source_format: SourceFormat
) -> tuple[tuple[CstNode, ...], tuple[RecoveryEvent, ...]]:
    html_mode = source_format is SourceFormat.HTML
    nodes: list[_MutableNode] = [
        _MutableNode(
            node_id=0,
            kind=NodeKind.DOCUMENT,
            parent_id=None,
            start_byte=0,
            end_byte=source_size,
        )
    ]
    stack = [0]
    events: list[RecoveryEvent] = []

    for token_index, token in enumerate(tokens):
        for issue in token.issues:
            events.append(RecoveryEvent("token-issue", token.start_byte, None, issue))

        if token.kind in {TokenKind.START_TAG, TokenKind.SELF_CLOSING_TAG}:
            name = token.name or ""
            compare_name = name.lower() if html_mode else name
            if html_mode and compare_name in _HTML_CLOSE_ON_START:
                _close_html_optional_nodes(
                    compare_name,
                    token.start_byte,
                    token_index,
                    stack,
                    nodes,
                    events,
                )
            node_id = _append_node(
                nodes,
                stack[-1],
                NodeKind.ELEMENT,
                token.start_byte,
                token.end_byte,
                token_index,
                name=name,
            )
            is_void = html_mode and compare_name in _HTML_VOID
            if token.kind is TokenKind.SELF_CLOSING_TAG or is_void:
                nodes[node_id].end_token_index = token_index
            else:
                stack.append(node_id)
            continue

        if token.kind is TokenKind.END_TAG:
            _apply_end_tag(token, token_index, html_mode, stack, nodes, events)
            continue

        node_kind = _node_kind(token.kind)
        _append_node(
            nodes,
            stack[-1],
            node_kind,
            token.start_byte,
            token.end_byte,
            token_index,
            end_token_index=token_index,
            name=token.name,
        )

    while len(stack) > 1:
        node_id = stack.pop()
        node = nodes[node_id]
        node.end_byte = source_size
        node.implicitly_closed = True
        events.append(
            RecoveryEvent(
                "implicit-close-at-eof",
                source_size,
                node_id,
                f"<{node.name}> had no closing tag",
            )
        )

    frozen = tuple(
        CstNode(
            node_id=node.node_id,
            kind=node.kind,
            parent_id=node.parent_id,
            child_ids=tuple(node.children),
            name=node.name,
            start_byte=node.start_byte,
            end_byte=node.end_byte,
            start_token_index=node.start_token_index,
            end_token_index=node.end_token_index,
            implicitly_closed=node.implicitly_closed,
        )
        for node in nodes
    )
    return frozen, tuple(events)


def _append_node(
    nodes: list[_MutableNode],
    parent_id: int,
    kind: NodeKind,
    start_byte: int,
    end_byte: int,
    start_token_index: int,
    *,
    end_token_index: int | None = None,
    name: str | None = None,
) -> int:
    node_id = len(nodes)
    nodes.append(
        _MutableNode(
            node_id=node_id,
            kind=kind,
            parent_id=parent_id,
            name=name,
            start_byte=start_byte,
            end_byte=end_byte,
            start_token_index=start_token_index,
            end_token_index=end_token_index,
        )
    )
    nodes[parent_id].children.append(node_id)
    return node_id


def _apply_end_tag(
    token: Token,
    token_index: int,
    html_mode: bool,
    stack: list[int],
    nodes: list[_MutableNode],
    events: list[RecoveryEvent],
) -> None:
    end_name = (token.name or "").lower() if html_mode else token.name or ""
    match_at: int | None = None
    for position in range(len(stack) - 1, 0, -1):
        open_name = nodes[stack[position]].name or ""
        if html_mode:
            open_name = open_name.lower()
        if open_name == end_name:
            match_at = position
            break

    if match_at is None:
        node_id = _append_node(
            nodes,
            stack[-1],
            NodeKind.RAW,
            token.start_byte,
            token.end_byte,
            token_index,
            end_token_index=token_index,
            name=token.name,
        )
        events.append(
            RecoveryEvent(
                "orphan-end-tag",
                token.start_byte,
                node_id,
                f"</{token.name}> has no open start tag",
            )
        )
        return

    while len(stack) - 1 > match_at:
        node_id = stack.pop()
        node = nodes[node_id]
        node.end_byte = token.start_byte
        node.implicitly_closed = True
        events.append(
            RecoveryEvent(
                "implicit-close-before-end-tag",
                token.start_byte,
                node_id,
                f"<{node.name}> closed before </{token.name}>",
            )
        )

    node_id = stack.pop()
    node = nodes[node_id]
    node.end_byte = token.end_byte
    node.end_token_index = token_index


def _close_html_optional_nodes(
    new_name: str,
    byte_offset: int,
    token_index: int,
    stack: list[int],
    nodes: list[_MutableNode],
    events: list[RecoveryEvent],
) -> None:
    closable = _HTML_CLOSE_ON_START[new_name]
    while len(stack) > 1:
        node_id = stack[-1]
        open_name = (nodes[node_id].name or "").lower()
        if open_name not in closable:
            break
        stack.pop()
        node = nodes[node_id]
        node.end_byte = byte_offset
        node.end_token_index = token_index - 1 if token_index else None
        node.implicitly_closed = True
        events.append(
            RecoveryEvent(
                "html-optional-close",
                byte_offset,
                node_id,
                f"<{node.name}> closed by <{new_name}>",
            )
        )


def _node_kind(token_kind: TokenKind) -> NodeKind:
    return {
        TokenKind.TEXT: NodeKind.TEXT,
        TokenKind.COMMENT: NodeKind.COMMENT,
        TokenKind.CDATA: NodeKind.CDATA,
        TokenKind.PROCESSING_INSTRUCTION: NodeKind.PROCESSING_INSTRUCTION,
        TokenKind.XML_DECLARATION: NodeKind.DECLARATION,
        TokenKind.DOCTYPE: NodeKind.DECLARATION,
        TokenKind.RAW: NodeKind.RAW,
    }[token_kind]
