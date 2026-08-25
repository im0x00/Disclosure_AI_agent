from pathlib import Path

from eval.models import ReviewStatus
from eval.runtime import render_review, validate_suite

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_seed_suite_is_raw_grounded_and_waiting_for_human_review() -> None:
    checks = validate_suite(
        PROJECT_ROOT / "eval" / "cases" / "seed.json",
        PROJECT_ROOT / "corpus",
    )

    assert len(checks) == 12
    assert sum(len(check.evidence) for check in checks) == 26
    assert all(check.case.review.status == ReviewStatus.DRAFT for check in checks)


def test_review_output_contains_raw_location_and_visible_text() -> None:
    checks = validate_suite(
        PROJECT_ROOT / "eval" / "cases" / "seed.json",
        PROJECT_ROOT / "corpus",
    )

    rendered = render_review(checks[0])

    assert "bytes: [6589, 6971)" in rendered
    assert "계약금액(원) 22,764,764,160,000" in rendered
