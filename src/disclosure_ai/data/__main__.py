"""Run corpus-wide losslessness verification."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict

from disclosure_ai.data.verify import verify_corpus


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", help="path to the corpus directory")
    parser.add_argument(
        "--exclude-list-sidecars",
        action="store_true",
        help="verify disclosure artifacts but skip list_*.json files",
    )
    args = parser.parse_args()
    summary = verify_corpus(
        args.corpus,
        include_list_sidecars=not args.exclude_list_sidecars,
    )
    print(json.dumps(asdict(summary), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
