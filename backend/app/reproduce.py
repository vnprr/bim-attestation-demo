"""Re-run the oracle's QA locally and print the three hashes.

Anyone holding the IFC file and the public IDS ruleset can compare the output with
`asset_hash`, `ruleset_hash` and `result_hash` stored in the milestone account on chain.

    uv run python -m app.reproduce ../demo/architecture_valid.ifc ../rules/ruleset_a_strict.ids
"""

import argparse
from pathlib import Path

from .qa import load_ruleset, run_qa


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("ifc", type=Path)
    parser.add_argument("ids", type=Path)
    args = parser.parse_args()

    report = run_qa(args.ifc.read_bytes(), load_ruleset(args.ids))
    result = report.result
    print(f"{'PASS' if result.passed else 'FAIL'}  ({report.ruleset_name}, {result.engine})")
    for v in result.violations:
        print(f"  - {v.rule}: {v.element} [{v.global_id}] {v.reason}")
    print(f"asset_hash   {result.asset_hash}")
    print(f"ruleset_hash {result.ruleset_hash}")
    print(f"result_hash  {report.result_hash}")


if __name__ == "__main__":
    main()
