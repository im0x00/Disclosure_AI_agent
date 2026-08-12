"""Lossless source catalog and structural parser."""

from disclosure_ai.data.adapters import EvidenceValue, StructuralDescriptor, describe
from disclosure_ai.data.catalog import CorpusCatalog, CorpusDocument
from disclosure_ai.data.models import (
    CstNode,
    ParsedArtifact,
    RecoveryEvent,
    SourceArtifact,
    SourceEnvelope,
    SourceFormat,
    Token,
    TokenKind,
)
from disclosure_ai.data.parser import parse_artifact
from disclosure_ai.data.semantic_ir import SCHEMA_VERSION, build_semantic_ir
from disclosure_ai.data.verify import VerificationSummary, verify_corpus

__all__ = [
    "CorpusCatalog",
    "CorpusDocument",
    "CstNode",
    "EvidenceValue",
    "ParsedArtifact",
    "RecoveryEvent",
    "SCHEMA_VERSION",
    "SourceArtifact",
    "SourceEnvelope",
    "SourceFormat",
    "StructuralDescriptor",
    "Token",
    "TokenKind",
    "VerificationSummary",
    "build_semantic_ir",
    "describe",
    "parse_artifact",
    "verify_corpus",
]
