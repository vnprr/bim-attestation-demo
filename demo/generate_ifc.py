"""Generate the three demo IFC files from one base model.

    cd backend && uv run python ../demo/generate_ifc.py

The generated files are committed. Re-running this script changes their bytes
(the IFC header holds a timestamp, GlobalIds are random), so asset hashes change too.
"""

from pathlib import Path

import ifcopenshell
import ifcopenshell.api.aggregate
import ifcopenshell.api.context
import ifcopenshell.api.project
import ifcopenshell.api.pset
import ifcopenshell.api.root
import ifcopenshell.api.spatial
import ifcopenshell.api.unit
import ifcopenshell.util.element

OUT = Path(__file__).parent
WALLS = [("W-01 North", True), ("W-02 East", True), ("W-03 South", True), ("W-04 Partition", False)]
SPACES = ["Office 1.01", "Office 1.02", "Meeting Room 1.03"]


def build_base() -> ifcopenshell.file:
    """A small office floor: 4 walls with fire rating, 3 named spaces. Passes the strict ruleset."""
    model = ifcopenshell.api.project.create_file(version="IFC4")
    create = lambda ifc_class, name: ifcopenshell.api.root.create_entity(model, ifc_class=ifc_class, name=name)

    project = create("IfcProject", "Demo Office")
    ifcopenshell.api.unit.assign_unit(model)
    ifcopenshell.api.context.add_context(model, context_type="Model")
    site, building, storey = create("IfcSite", "Site"), create("IfcBuilding", "Office"), create("IfcBuildingStorey", "Level 1")
    ifcopenshell.api.aggregate.assign_object(model, relating_object=project, products=[site])
    ifcopenshell.api.aggregate.assign_object(model, relating_object=site, products=[building])
    ifcopenshell.api.aggregate.assign_object(model, relating_object=building, products=[storey])

    walls = []
    for name, external in WALLS:
        wall = create("IfcWall", name)
        pset = ifcopenshell.api.pset.add_pset(model, product=wall, name="Pset_WallCommon")
        ifcopenshell.api.pset.edit_pset(model, pset=pset, properties={"FireRating": "REI60", "IsExternal": external})
        walls.append(wall)
    ifcopenshell.api.spatial.assign_container(model, relating_structure=storey, products=walls)

    spaces = [create("IfcSpace", name) for name in SPACES]
    ifcopenshell.api.aggregate.assign_object(model, relating_object=storey, products=spaces)
    return model


def set_wall_property(model: ifcopenshell.file, wall_name: str, prop: str, value) -> None:
    wall = next(w for w in model.by_type("IfcWall") if w.Name == wall_name)
    pset_id = ifcopenshell.util.element.get_psets(wall)["Pset_WallCommon"]["id"]
    ifcopenshell.api.pset.edit_pset(model, pset=model.by_id(pset_id), properties={prop: value})


def main() -> None:
    valid = OUT / "architecture_valid.ifc"
    build_base().write(str(valid))

    broken = ifcopenshell.open(str(valid))
    set_wall_property(broken, "W-02 East", "FireRating", None)
    set_wall_property(broken, "W-04 Partition", "FireRating", None)
    next(s for s in broken.by_type("IfcSpace") if s.Name == "Office 1.02").Name = None
    broken.write(str(OUT / "architecture_broken.ifc"))

    modified = ifcopenshell.open(str(valid))
    set_wall_property(modified, "W-01 North", "FireRating", "REI90")
    modified.write(str(OUT / "architecture_modified.ifc"))
    print("written:", *sorted(p.name for p in OUT.glob("*.ifc")))


if __name__ == "__main__":
    main()
