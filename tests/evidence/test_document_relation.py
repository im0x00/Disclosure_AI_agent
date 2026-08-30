from pathlib import Path

import pytest
from pydantic import ValidationError

from evidence.compiler import compile_document_tree
from evidence.document_grain import DocumentGrain
from evidence.document_relation import (
    SIGNAL_PREDICATES,
    DocumentRelation,
    RelationPredicate,
    RelationSignal,
    UnsupportedRelationSignals,
    manifest_relation_signals,
    predicate_for_signal,
    relations_affected_by_grain_rebuild,
    require_predicate_coverage,
    tree_relation_signals,
    validate_relation_grains,
)
from evidence.document_tree import DocumentTree
from evidence.grain_compiler import compile_document_grains
from evidence.loader import read_documents

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CORPUS_ROOT = PROJECT_ROOT / "corpus"


def compile_fixture(tmp_path: Path, receipt_no: str, body: str) -> DocumentTree:
    source_directory = tmp_path / receipt_no
    source_directory.mkdir()
    source = source_directory / f"{receipt_no}.xml"
    source.write_text(f"<DOCUMENT><BODY>{body}</BODY></DOCUMENT>", encoding="utf-8")
    return compile_document_tree(
        source,
        doc_id=f"major_{receipt_no}",
        corpus_root=tmp_path,
    )


def grains_by_id(*groups: tuple[DocumentGrain, ...]) -> dict[str, DocumentGrain]:
    return {grain.grain_id: grain for group in groups for grain in group}


def test_document_relation_defaults_to_whole_documents() -> None:
    relation = DocumentRelation(
        source_doc_id="exchange_20240101000001",
        predicate=RelationPredicate.REVISES,
        target_doc_id="exchange_20231231000001",
    )

    assert relation.source_grain_ids == ()
    assert relation.target_grain_ids == ()
    validate_relation_grains(relation, grains_by_id={})


def test_document_relation_rejects_self_relation_and_unknown_predicate() -> None:
    with pytest.raises(ValidationError, match="two different documents"):
        DocumentRelation(
            source_doc_id="major_20240101000001",
            predicate=RelationPredicate.REFERENCES,
            target_doc_id="major_20240101000001",
        )

    with pytest.raises(ValidationError):
        DocumentRelation.model_validate(
            {
                "source_doc_id": "major_20240101000001",
                "predicate": "extends",
                "target_doc_id": "major_20231231000001",
            }
        )


def test_document_relation_requires_an_in_corpus_target() -> None:
    with pytest.raises(ValidationError, match="target_doc_id"):
        DocumentRelation.model_validate(
            {
                "source_doc_id": "major_20240101000001",
                "predicate": RelationPredicate.REFERENCES,
            }
        )

    with pytest.raises(ValidationError, match="external_target"):
        DocumentRelation.model_validate(
            {
                "source_doc_id": "major_20240101000001",
                "predicate": RelationPredicate.REFERENCES,
                "target_doc_id": "major_20231231000001",
                "external_target": "20220101000001",
            }
        )


def test_optional_grain_endpoints_resolve_to_their_owning_documents(
    tmp_path: Path,
) -> None:
    source_tree = compile_fixture(
        tmp_path,
        "20240101000001",
        "<P>source</P><TABLE><TR><TD>source table</TD></TR></TABLE>",
    )
    target_tree = compile_fixture(
        tmp_path,
        "20231231000001",
        "<P>target</P><TABLE><TR><TD>target table</TD></TR></TABLE>",
    )
    source_grains = compile_document_grains(source_tree)
    target_grains = compile_document_grains(target_tree)
    relation = DocumentRelation(
        source_doc_id=source_tree.doc_id,
        predicate=RelationPredicate.TERMINATES,
        target_doc_id=target_tree.doc_id,
        source_grain_ids=(source_grains[0].grain_id,),
        target_grain_ids=tuple(grain.grain_id for grain in target_grains),
    )

    validate_relation_grains(
        relation,
        grains_by_id=grains_by_id(source_grains, target_grains),
    )

    wrong_owner = relation.model_copy(update={"target_grain_ids": (source_grains[0].grain_id,)})
    with pytest.raises(ValueError, match="owned by another document"):
        validate_relation_grains(
            wrong_owner,
            grains_by_id=grains_by_id(source_grains, target_grains),
        )


def test_grain_endpoints_reject_duplicates_stale_ids_and_wrong_order(
    tmp_path: Path,
) -> None:
    source_tree = compile_fixture(
        tmp_path,
        "20240101000001",
        "<P>source</P><TABLE><TR><TD>source table</TD></TR></TABLE>",
    )
    target_tree = compile_fixture(tmp_path, "20231231000001", "<P>target</P>")
    source_grains = compile_document_grains(source_tree)
    target_grains = compile_document_grains(target_tree)
    assert len(source_grains) >= 2
    inventory = grains_by_id(source_grains, target_grains)

    with pytest.raises(ValidationError, match="must not contain duplicates"):
        DocumentRelation(
            source_doc_id=source_tree.doc_id,
            source_grain_ids=(source_grains[0].grain_id, source_grains[0].grain_id),
            predicate=RelationPredicate.REFERENCES,
            target_doc_id=target_tree.doc_id,
        )

    stale = DocumentRelation(
        source_doc_id=source_tree.doc_id,
        source_grain_ids=("0" * 64,),
        predicate=RelationPredicate.REFERENCES,
        target_doc_id=target_tree.doc_id,
    )
    with pytest.raises(ValueError, match="unknown grain_id"):
        validate_relation_grains(stale, grains_by_id=inventory)

    wrong_order = DocumentRelation(
        source_doc_id=source_tree.doc_id,
        source_grain_ids=(source_grains[1].grain_id, source_grains[0].grain_id),
        predicate=RelationPredicate.REFERENCES,
        target_doc_id=target_tree.doc_id,
    )
    with pytest.raises(ValueError, match="follow document order"):
        validate_relation_grains(wrong_order, grains_by_id=inventory)


def test_grain_rebuild_invalidates_incoming_and_outgoing_relations() -> None:
    outgoing = DocumentRelation(
        source_doc_id="exchange_20240101000001",
        predicate=RelationPredicate.REVISES,
        target_doc_id="exchange_20231231000001",
    )
    incoming = DocumentRelation(
        source_doc_id="exchange_20240201000001",
        predicate=RelationPredicate.REFERENCES,
        target_doc_id="exchange_20240101000001",
    )
    unrelated = DocumentRelation(
        source_doc_id="major_20240301000001",
        predicate=RelationPredicate.TERMINATES,
        target_doc_id="major_20230201000001",
    )

    assert relations_affected_by_grain_rebuild(
        (outgoing, incoming, unrelated),
        {"exchange_20240101000001"},
    ) == (outgoing, incoming)


def test_tree_signals_find_corrections_and_related_disclosures(tmp_path: Path) -> None:
    tree = compile_fixture(
        tmp_path,
        "20240101000001",
        (
            "<CORRECTION><P>changed</P></CORRECTION>"
            '<A HREF="https://kind.example/view?rcpno=20231231000001">related</A>'
        ),
    )

    assert tree_relation_signals(tree) == {
        RelationSignal.IS_CORRECTION,
        RelationSignal.RELATED_DISCLOSURE,
    }


def test_manifest_signals_find_corrections_and_terminations() -> None:
    signals = manifest_relation_signals(
        {
            "is_correction": True,
            "doc_subtype": "단일판매공급계약해지",
            "report_name": "[기재정정]단일판매ㆍ공급계약해지",
        }
    )

    assert signals == {
        RelationSignal.IS_CORRECTION,
        RelationSignal.TERMINATION,
    }


def test_every_predicate_has_a_discovery_signal() -> None:
    assert set(SIGNAL_PREDICATES.values()) == set(RelationPredicate)


def test_coverage_invariant_names_an_unmapped_relation_signal() -> None:
    with pytest.raises(UnsupportedRelationSignals, match="contract_extension") as error:
        require_predicate_coverage(
            {
                RelationSignal.IS_CORRECTION,
                RelationSignal.RELATED_DISCLOSURE,
                RelationSignal.TERMINATION,
                "contract_extension",
            }
        )

    assert error.value.signals == ("contract_extension",)


def test_current_corpus_manifest_signals_have_predicates() -> None:
    observed = {
        signal
        for document in read_documents(CORPUS_ROOT)
        for signal in manifest_relation_signals(document)
    }

    require_predicate_coverage(observed)
    assert observed == {
        RelationSignal.IS_CORRECTION,
        RelationSignal.TERMINATION,
    }


@pytest.mark.parametrize(
    ("signal", "predicate"),
    [
        (RelationSignal.IS_CORRECTION, RelationPredicate.REVISES),
        (RelationSignal.RELATED_DISCLOSURE, RelationPredicate.REFERENCES),
        (RelationSignal.TERMINATION, RelationPredicate.TERMINATES),
    ],
)
def test_signal_maps_to_predicate(
    signal: RelationSignal,
    predicate: RelationPredicate,
) -> None:
    assert predicate_for_signal(signal) == predicate
