"""Evidence-linked structural descriptors for each disclosure family."""

from __future__ import annotations

from dataclasses import dataclass

from disclosure_ai.data.models import NodeKind, ParsedArtifact


@dataclass(frozen=True, slots=True)
class EvidenceValue:
    raw: bytes
    text: str
    start_byte: int
    end_byte: int


@dataclass(frozen=True, slots=True)
class StructuralDescriptor:
    adapter: str
    document_name: EvidenceValue | None
    document_code: EvidenceValue | None
    company_name: EvidenceValue | None
    company_code: EvidenceValue | None
    formula_version: EvidenceValue | None
    schema_location: EvidenceValue | None
    html_title: EvidenceValue | None


def describe(parsed: ParsedArtifact) -> StructuralDescriptor:
    group = parsed.source.envelope.doc_group
    adapter = group if group in {"periodic", "major", "holding", "exchange"} else "generic"
    if adapter == "exchange":
        return StructuralDescriptor(
            adapter=adapter,
            document_name=None,
            document_code=None,
            company_name=None,
            company_code=None,
            formula_version=None,
            schema_location=None,
            html_title=_element_value(parsed, "title", case_insensitive=True),
        )
    return StructuralDescriptor(
        adapter=adapter,
        document_name=_element_value(parsed, "DOCUMENT-NAME"),
        document_code=_attribute_value(parsed, "DOCUMENT-NAME", "ACODE"),
        company_name=_element_value(parsed, "COMPANY-NAME"),
        company_code=_attribute_value(parsed, "COMPANY-NAME", "AREGCIK"),
        formula_version=_element_value(parsed, "FORMULA-VERSION"),
        schema_location=_attribute_value(parsed, "DOCUMENT", "xsi:noNamespaceSchemaLocation"),
        html_title=None,
    )


def _element_value(
    parsed: ParsedArtifact, name: str, *, case_insensitive: bool = False
) -> EvidenceValue | None:
    for node in parsed.nodes:
        if node.kind is not NodeKind.ELEMENT or node.name is None:
            continue
        matches = node.name.lower() == name.lower() if case_insensitive else node.name == name
        if not matches or node.start_token_index is None:
            continue
        start_token = parsed.tokens[node.start_token_index]
        if node.end_token_index is None:
            end = node.end_byte
        else:
            end_token = parsed.tokens[node.end_token_index]
            end = end_token.start_byte if end_token is not start_token else start_token.end_byte
        start = start_token.end_byte
        raw = parsed.source.content[start:end]
        return EvidenceValue(raw=raw, text=_decode(raw), start_byte=start, end_byte=end)
    return None


def _attribute_value(
    parsed: ParsedArtifact, element_name: str, attribute_name: str
) -> EvidenceValue | None:
    for token in parsed.tokens:
        if token.name != element_name:
            continue
        for attribute in token.attributes:
            if attribute.name != attribute_name or attribute.value_start_byte is None:
                continue
            start = attribute.value_start_byte
            end = attribute.value_end_byte if attribute.value_end_byte is not None else start
            raw = parsed.source.content[start:end]
            return EvidenceValue(raw=raw, text=_decode(raw), start_byte=start, end_byte=end)
    return None


def _decode(raw: bytes) -> str:
    return raw.decode("utf-8", errors="replace")
