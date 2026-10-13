"""QA engine: validate an IFC model against an IDS ruleset and fingerprint the outcome."""

from pathlib import Path

import ifcopenshell
import ifctester
from ifctester import ids

from .hashing import canonical_json, sha256_hex
from .schemas import QaReport, QaResult, Ruleset, Violation

ENGINE = f"ifctester {ifctester.__version__}"


def load_ruleset(path: Path) -> Ruleset:
    """The ruleset hash is the SHA-256 of the IDS file bytes: the file itself is the contract."""
    return Ruleset(name=ids.open(str(path)).info["title"], hash=sha256_hex(path.read_bytes()), path=path)


def load_rulesets(rules_dir: Path) -> dict[str, Ruleset]:
    """Registry of all known rulesets, keyed by hash."""
    rulesets = (load_ruleset(path) for path in sorted(rules_dir.glob("*.ids")))
    return {r.hash: r for r in rulesets}


def run_qa(ifc_bytes: bytes, ruleset: Ruleset) -> QaReport:
    spec = ids.open(str(ruleset.path))  # parsed fresh: validate() stores results on the objects
    spec.validate(_open_model(ifc_bytes))

    violations = sorted(
        (v for specification in spec.specifications for v in _violations(specification)),
        key=lambda v: (v.rule, v.global_id),
    )
    result = QaResult(
        engine=ENGINE,
        asset_hash=sha256_hex(ifc_bytes),
        ruleset_hash=ruleset.hash,
        passed=all(specification.status for specification in spec.specifications),
        violations=violations,
    )
    return QaReport(
        ruleset_name=ruleset.name,
        result=result,
        result_hash=sha256_hex(canonical_json(result.model_dump())),
    )


def _open_model(ifc_bytes: bytes) -> ifcopenshell.file:
    try:
        model = ifcopenshell.file.from_string(ifc_bytes.decode())
        model.schema  # garbage parses into an empty file without a schema; this raises
    except (UnicodeDecodeError, RuntimeError) as error:
        raise ValueError("Not a readable IFC file") from error
    return model


def _violations(specification: ids.Specification) -> list[Violation]:
    failures = [failure for requirement in specification.requirements for failure in requirement.failures]
    if not specification.status and not failures:
        # Required specification (minOccurs=1) but the model has nothing it applies to,
        # e.g. an empty model. Without minOccurs=1 an empty model would pass every rule.
        return [Violation(rule=specification.name, global_id="", element="-", reason="No elements this rule applies to")]
    return [
        Violation(
            rule=specification.name,
            global_id=failure["element"].GlobalId,
            element=failure["element"].Name or failure["element"].is_a(),
            reason=failure["reason"],
        )
        for failure in failures
    ]
