from collections import Counter

import ifcopenshell.api.project
import ifcopenshell.api.root
import pytest

from app.config import ROOT, RULES_DIR
from app.hashing import canonical_json, sha256_hex
from app.qa import load_ruleset, load_rulesets, run_qa

DEMO = ROOT / "demo"
STRICT = load_ruleset(RULES_DIR / "ruleset_a_strict.ids")
LENIENT = load_ruleset(RULES_DIR / "ruleset_b_lenient.ids")


def qa(name: str, ruleset=STRICT):
    return run_qa((DEMO / f"architecture_{name}.ifc").read_bytes(), ruleset)


def test_valid_passes_strict():
    report = qa("valid")
    assert report.result.passed
    assert report.result.violations == []


def test_broken_fails_strict_for_expected_rules():
    result = qa("broken").result
    assert not result.passed
    assert Counter(v.rule for v in result.violations) == {
        "Every wall has a fire rating": 2,
        "Every space has a name": 1,
    }


def test_broken_passes_lenient():
    """Needed for the attack scene: the easier ruleset would accept the broken model."""
    assert qa("broken", LENIENT).result.passed


@pytest.mark.parametrize("name", ["valid", "broken"])
def test_hashes_are_deterministic(name):
    first, second = qa(name), qa(name)
    assert first.model_dump() == second.model_dump()
    assert canonical_json(first.result.model_dump()) == canonical_json(second.result.model_dump())


def test_violations_are_sorted():
    violations = qa("broken").result.violations
    assert violations == sorted(violations, key=lambda v: (v.rule, v.global_id))


def test_modified_file_changes_asset_and_result_hash():
    valid, modified = qa("valid"), qa("modified")
    assert modified.result.passed
    assert modified.result.asset_hash != valid.result.asset_hash
    assert modified.result_hash != valid.result_hash


def test_result_binds_file_and_ruleset():
    result = qa("broken").result
    assert result.asset_hash == sha256_hex((DEMO / "architecture_broken.ifc").read_bytes())
    assert result.ruleset_hash == STRICT.hash


def test_empty_model_fails():
    """IDS 'every wall must…' is vacuously true without walls; minOccurs=1 closes that hole."""
    model = ifcopenshell.api.project.create_file(version="IFC4")
    ifcopenshell.api.root.create_entity(model, ifc_class="IfcProject", name="Empty")
    result = run_qa(model.to_string().encode(), STRICT).result
    assert not result.passed
    assert len(result.violations) == 3


def test_garbage_is_rejected():
    with pytest.raises(ValueError):
        run_qa(b"definitely not IFC", STRICT)


@pytest.mark.parametrize("path", sorted(DEMO.glob("*.ifc")) + sorted(RULES_DIR.glob("*.ids")), ids=lambda p: p.name)
def test_hashed_files_have_no_crlf(path):
    """A CRLF checkout (Windows autocrlf) changes every hash and breaks `reproduce` vs chain."""
    assert b"\r" not in path.read_bytes(), f"{path.name} has CRLF line endings: re-checkout after .gitattributes"


def test_registry_is_keyed_by_file_hash():
    registry = load_rulesets(RULES_DIR)
    assert set(registry) == {STRICT.hash, LENIENT.hash}
    assert registry[STRICT.hash].name == "Design Delivery - Strict"


def test_canonical_json_ignores_key_order():
    assert canonical_json({"b": 1, "a": [1, 2]}) == canonical_json({"a": [1, 2], "b": 1}) == b'{"a":[1,2],"b":1}'
