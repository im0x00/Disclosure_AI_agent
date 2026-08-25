from __future__ import annotations

import argparse
from pathlib import Path

from .models import ReviewStatus
from .runtime import render_review, suite_summary, validate_suite


def main() -> int:
    parser = argparse.ArgumentParser(description="Review raw-grounded eval cases")
    parser.add_argument(
        "command",
        choices=("list", "validate", "review", "ready"),
    )
    parser.add_argument("case_id", nargs="?")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    args = parser.parse_args()

    project_root = args.project_root.resolve()
    checks = validate_suite(
        project_root / "eval" / "cases" / "seed.json",
        project_root / "corpus",
    )

    if args.command == "list":
        for check in checks:
            case = check.case
            print(f"{case.case_id}\t{case.bucket}\t{case.review.status}\t{case.question}")
        return 0
    if args.command == "validate":
        print(suite_summary(checks))
        return 0
    if args.command == "review":
        if not args.case_id:
            parser.error("review requires case_id")
        match = next((check for check in checks if check.case.case_id == args.case_id), None)
        if match is None:
            parser.error(f"unknown case_id: {args.case_id}")
        print(render_review(match))
        return 0

    unapproved = [
        check.case.case_id for check in checks if check.case.review.status != ReviewStatus.APPROVED
    ]
    if unapproved:
        print("not ready; direct review required: " + ", ".join(unapproved))
        return 1
    print(suite_summary(checks))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
