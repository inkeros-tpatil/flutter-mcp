#!/usr/bin/env python3
"""Parse demo_app/lib Dart files and ingest AST nodes/edges into Memgraph.

Run this once (or after code changes) from the host to populate the graph:

    cd pipeline
    python ingest_ast.py

Environment variables
---------------------
MEMGRAPH_URI   bolt://localhost:7687  (default)
DEMO_APP_PATH  path to demo_app/lib   (default: ../demo_app/lib)

Idempotent — MERGE is used throughout so re-running is safe.

Graph schema
------------
Nodes
  (:File  {path, name, layer, feature, sublayer})
  (:Class {name, kind, role, is_abstract, file_path})
    + semantic multi-labels added by role:
        Screen, Widget, BlocClass, StateClass, EventClass,
        Entity, Model, UseCase, Repository, DataSource
  (:Prop  {owner, owner_file, name, type, required})

Relationships
  (File)   -[:DEFINES]                    -> (Class)
  (File)   -[:IMPORTS]                    -> (File)
  (Class)  -[:EXTENDS]                    -> (Class)
  (Class)  -[:IMPLEMENTS]                 -> (Class)
  (Class)  -[:MIXES_IN]                   -> (Class)
  (Class)  -[:DEPENDS_ON {field}]         -> (Class)
  (Class)  -[:HAS_PROP {required}]        -> (Prop)
  (Prop)   -[:OF_TYPE]                    -> (Class)
  (Screen|Widget) -[:USES_BLOC]           -> (BlocClass)
  (BlocClass) -[:EMITS]                   -> (StateClass)
  (BlocClass) -[:HANDLES]                 -> (EventClass)
  (Screen) -[:NAVIGATES_TO {route}]       -> (Screen)
  (Screen|Widget) -[:CONTAINS]            -> (Widget)
"""
import argparse
import os
import re
import sys
from pathlib import Path

from neo4j import GraphDatabase

# ---------------------------------------------------------------------------
# Regexes
# ---------------------------------------------------------------------------

_BLOCK_COMMENT    = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT     = re.compile(r"//[^\n]*")
_IMPORT_RE        = re.compile(r"""import\s+['"]([^'"]+)['"]\s*;""")

_CLASS_DECL_RE    = re.compile(
    r"(?:^|\n)[ \t]*"
    r"(?P<abstract>abstract\s+)?"
    r"(?P<kind>class|mixin|enum)\s+"
    r"(?P<name>\w+)"
    r"(?:<[^>]*>)?"
    r"(?P<rest>[^{]*)\{",
    re.MULTILINE,
)

_EXTENDS_RE       = re.compile(r"\bextends\s+([\w<>, ]+?)(?:\s+with\b|\s+implements\b|\s*$)")
_WITH_RE          = re.compile(r"\bwith\s+([\w<>, ]+?)(?:\s+implements\b|\s*$)")
_IMPLEMENTS_RE    = re.compile(r"\bimplements\s+([\w<>, ]+?)(?:\s*$)")

# Props: final fields with PascalCase type + required constructor params
_FINAL_FIELD_RE   = re.compile(r"\bfinal\s+([A-Z]\w*?)(?:<[^>]*>)?\s+(\w+)\s*;")
_REQUIRED_RE      = re.compile(r"\brequired\s+this\.(\w+)")

# Extended relationship detection (all applied to per-class body text)
_CONTEXT_BLOC_RE  = re.compile(r"context\.(?:read|watch|select)<(\w+)>\s*\(")
_NAVIGATE_RE      = re.compile(r"Navigator\.\w*Named\s*\(\s*\w+\s*,\s*([\w.]+)")
_BLOC_GENERIC_RE  = re.compile(r"\bBloc<(\w+)\s*,\s*(\w+)>")
_CUBIT_GENERIC_RE = re.compile(r"\bCubit<(\w+)>")
_PRIVATE_WIDGET_RE = re.compile(r"\b(_[A-Z]\w+)\s*\(")

# Router file: constant declarations and switch-case→class mappings
_ROUTE_CONST_RE   = re.compile(
    r"static\s+const\s+String\s+(\w+)\s*=\s*['\"]([^'\"]+)['\"]"
)
_ROUTE_CASE_RE    = re.compile(
    r"case\s+(\w+)\s*:.*?=>\s*(?:const\s+)?([A-Z]\w+)\s*[({]",
    re.DOTALL,
)

# Role → extra Cypher label applied to the :Class node
_ROLE_LABEL: dict[str, str] = {
    "page":            "Screen",
    "widget":          "Widget",
    "widget_state":    "Widget",
    "bloc":            "BlocClass",
    "cubit":           "BlocClass",
    "state":           "StateClass",
    "state_base":      "StateClass",
    "event":           "EventClass",
    "event_base":      "EventClass",
    "entity":          "Entity",
    "model":           "Model",
    "usecase":         "UseCase",
    "usecase_base":    "UseCase",
    "repository":      "Repository",
    "repository_impl": "Repository",
    "datasource":      "DataSource",
    "datasource_impl": "DataSource",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_comments(src: str) -> str:
    src = _BLOCK_COMMENT.sub("", src)
    return _LINE_COMMENT.sub("", src)


def _strip_generics(s: str) -> str:
    """'Bloc<AuthEvent, AuthState>' → 'Bloc'"""
    depth, buf = 0, []
    for ch in s:
        if ch == "<":    depth += 1
        elif ch == ">":  depth -= 1
        elif depth == 0: buf.append(ch)
    return "".join(buf)


def _name_list(s: str) -> list[str]:
    return [n.strip() for n in _strip_generics(s).split(",") if n.strip()]


def _extract_class_bodies(clean_src: str, class_matches: list) -> dict[str, str]:
    """Return {class_name: body_text} for each class match using brace counting."""
    bodies: dict[str, str] = {}
    for m in class_matches:
        name       = m.group("name")
        open_brace = m.end() - 1    # position of the opening {
        depth      = 0
        for i in range(open_brace, len(clean_src)):
            if clean_src[i] == "{":
                depth += 1
            elif clean_src[i] == "}":
                depth -= 1
                if depth == 0:
                    bodies[name] = clean_src[open_brace + 1 : i]
                    break
    return bodies


# ---------------------------------------------------------------------------
# Path classification
# ---------------------------------------------------------------------------

def _classify_path(rel_path: str) -> tuple[str, str | None, str | None]:
    """Return (layer, feature, sublayer) from a lib-relative path."""
    parts = Path(rel_path).parts
    if "features" in parts:
        idx     = parts.index("features")
        feature = parts[idx + 1] if idx + 1 < len(parts) else None
        for sub in ("domain", "data", "presentation"):
            if sub in parts:
                return "feature", feature, sub
        return "feature", feature, None
    elif "core" in parts:
        return "core", None, None
    return "root", None, None


def _determine_role(
    name: str,
    rel_path: str,
    is_abstract: bool,
    kind: str,
    extends: str | None,
    implements: list[str],
) -> str:
    parts = set(Path(rel_path).parts)
    stem  = Path(rel_path).stem

    if kind == "enum":  return "enum"
    if kind == "mixin": return "mixin"

    # State classes are always widget_state regardless of directory
    if extends == "State":
        return "widget_state"

    if "entities"     in parts: return "entity"
    if "models"       in parts or stem.endswith("_model"):  return "model"
    if "repositories" in parts:
        return "repository" if is_abstract or not name.endswith("Impl") else "repository_impl"
    if "datasources"  in parts:
        return "datasource" if is_abstract else "datasource_impl"
    if "usecases"     in parts:
        return "usecase_base" if is_abstract else "usecase"
    if "pages"        in parts or stem.endswith("_page"):
        # Private _ classes co-located in a page file are widgets, not pages
        if name.startswith("_") and extends in ("StatelessWidget", "StatefulWidget"):
            return "widget"
        return "page"
    if "bloc"         in parts:
        if stem.endswith("_bloc"):  return "bloc"
        if stem.endswith("_cubit"): return "cubit"
        if stem.endswith("_event"): return "event_base" if is_abstract else "event"
        if stem.endswith("_state"): return "state_base" if is_abstract else "state"
    if "routes"       in parts: return "router"
    if "theme"        in parts: return "theme"

    if extends:
        if extends in ("StatefulWidget", "StatelessWidget"): return "widget"
        if "Bloc"  in extends:                               return "bloc"
        if "Cubit" in extends:                               return "cubit"

    return "other"


# ---------------------------------------------------------------------------
# Per-file parser
# ---------------------------------------------------------------------------

def parse_dart_file(path: Path, lib_root: Path) -> dict:
    src   = path.read_text(encoding="utf-8", errors="replace")
    clean = _strip_comments(src)
    rel   = str(path.relative_to(lib_root)).replace("\\", "/")
    layer, feature, sublayer = _classify_path(rel)

    class_matches = list(_CLASS_DECL_RE.finditer(clean))
    class_bodies  = _extract_class_bodies(clean, class_matches)

    # Imports
    imports: list[str] = []
    for m in _IMPORT_RE.finditer(clean):
        resolved = _resolve_import(m.group(1), rel)
        if resolved:
            imports.append(resolved)

    # Classes
    classes: list[dict] = []
    for m in class_matches:
        nm          = m.group("name")
        is_abstract = bool(m.group("abstract"))
        kind        = m.group("kind")
        rest        = m.group("rest") or ""

        extends_raw = None
        extends     = None
        if em := _EXTENDS_RE.search(rest):
            extends_raw = em.group(1).strip()
            names   = _name_list(extends_raw)
            extends = names[0] if names else None

        with_mixins: list[str] = []
        if wm := _WITH_RE.search(rest):
            with_mixins = _name_list(wm.group(1))

        ifaces: list[str] = []
        if im := _IMPLEMENTS_RE.search(rest):
            ifaces = _name_list(im.group(1))

        role = _determine_role(nm, rel, is_abstract, kind, extends, ifaces)

        # EMITS + HANDLES: parse Bloc<EventType, StateType> generic params
        emits_state:   str | None = None
        handles_event: str | None = None
        if extends_raw:
            if bg := _BLOC_GENERIC_RE.search(extends_raw):
                handles_event = bg.group(1)
                emits_state   = bg.group(2)
            elif cg := _CUBIT_GENERIC_RE.search(extends_raw):
                emits_state = cg.group(1)

        # Per-class body analysis
        body = class_bodies.get(nm, "")

        # Props: final PascalCase fields + which are required in constructor
        field_types: dict[str, str] = {
            fm.group(2): fm.group(1)
            for fm in _FINAL_FIELD_RE.finditer(body)
        }
        required_set = set(_REQUIRED_RE.findall(body))
        props: list[dict] = [
            {"name": fn, "type": ft, "required": fn in required_set}
            for fn, ft in field_types.items()
        ]

        # Extended relationship targets — scoped to this class's body
        uses_blocs       = list(set(_CONTEXT_BLOC_RE.findall(body)))
        nav_targets      = list(set(_NAVIGATE_RE.findall(body)))
        contains_widgets = list(set(_PRIVATE_WIDGET_RE.findall(body)))

        classes.append({
            "name":             nm,
            "kind":             kind,
            "is_abstract":      is_abstract,
            "role":             role,
            "file_path":        rel,
            "extends":          extends,
            "with":             with_mixins,
            "implements":       ifaces,
            "emits_state":      emits_state,
            "handles_event":    handles_event,
            "props":            props,
            "uses_blocs":       uses_blocs,
            "nav_targets":      nav_targets,
            "contains_widgets": contains_widgets,
        })

    # Route constants + case→class mapping (router files only)
    route_consts:  dict[str, str] = {}
    route_nav_map: dict[str, str] = {}
    if any(c["role"] == "router" for c in classes):
        for m in _ROUTE_CONST_RE.finditer(clean):
            route_consts[m.group(1)] = m.group(2)
        for m in _ROUTE_CASE_RE.finditer(clean):
            route_nav_map[m.group(1)] = m.group(2)

    # File-level field deps (kept for DEPENDS_ON compatibility)
    field_deps: list[dict] = [
        {"type": m.group(1), "field": m.group(2)}
        for m in _FINAL_FIELD_RE.finditer(clean)
    ]

    return {
        "path":          rel,
        "name":          path.name,
        "layer":         layer,
        "feature":       feature,
        "sublayer":      sublayer,
        "imports":       imports,
        "classes":       classes,
        "field_deps":    field_deps,
        "route_consts":  route_consts,
        "route_nav_map": route_nav_map,
    }


def _resolve_import(raw: str, current_file: str) -> str | None:
    """Resolve an import string to a lib-relative .dart path, or None if external."""
    if raw.startswith("dart:"):
        return None
    if raw.startswith("package:demo_app/"):
        return raw[len("package:demo_app/"):]
    if raw.startswith("package:"):
        return None
    base_parts = current_file.split("/")[:-1]
    for seg in raw.split("/"):
        if seg == "..":
            if base_parts:
                base_parts.pop()
        elif seg and seg != ".":
            base_parts.append(seg)
    return "/".join(base_parts) if base_parts else None


# ---------------------------------------------------------------------------
# Memgraph ingestion — Cypher queries
# ---------------------------------------------------------------------------

SCHEMA_QUERIES = [
    "CREATE INDEX ON :File(path);",
    "CREATE INDEX ON :Class(name);",
    "CREATE INDEX ON :Class(file_path);",
    "CREATE INDEX ON :Prop(owner);",
]

CLEAR_QUERY = "MATCH (n) WHERE n:File OR n:Class OR n:Prop DETACH DELETE n"

UPSERT_FILE = """
MERGE (f:File {path: $path})
SET f.name     = $name,
    f.layer    = $layer,
    f.feature  = $feature,
    f.sublayer = $sublayer
"""

UPSERT_CLASS = """
MERGE (c:Class {name: $name, file_path: $file_path})
SET c.kind        = $kind,
    c.is_abstract = $is_abstract,
    c.role        = $role
"""

# Formatted with .format(label=...) — label comes from _ROLE_LABEL, never user input
ADD_SEMANTIC_LABEL = (
    "MATCH (c:Class {{name: $name, file_path: $fp}}) SET c:{label}"
)

LINK_DEFINES = """
MATCH (f:File {path: $file_path})
MATCH (c:Class {name: $class_name, file_path: $file_path})
MERGE (f)-[:DEFINES]->(c)
"""

LINK_IMPORT = """
MATCH (a:File {path: $from_path})
MATCH (b:File {path: $to_path})
MERGE (a)-[:IMPORTS]->(b)
"""

LINK_EXTENDS = """
MATCH (child:Class {name: $child, file_path: $child_path})
MATCH (parent:Class {name: $parent})
MERGE (child)-[:EXTENDS]->(parent)
"""

LINK_IMPLEMENTS = """
MATCH (child:Class {name: $child, file_path: $child_path})
MATCH (iface:Class {name: $iface})
MERGE (child)-[:IMPLEMENTS]->(iface)
"""

LINK_MIXES_IN = """
MATCH (child:Class {name: $child, file_path: $child_path})
MATCH (mix:Class {name: $mix})
MERGE (child)-[:MIXES_IN]->(mix)
"""

LINK_DEPENDS_ON = """
MATCH (owner:Class {file_path: $file_path})
MATCH (dep:Class {name: $dep_type})
MERGE (owner)-[:DEPENDS_ON {field: $field}]->(dep)
"""

# Props
UPSERT_PROP = """
MERGE (p:Prop {owner: $owner, owner_file: $owner_file, name: $prop_name})
SET p.type     = $prop_type,
    p.required = $required
"""

LINK_HAS_PROP = """
MATCH (c:Class {name: $owner, file_path: $owner_file})
MATCH (p:Prop  {owner: $owner, owner_file: $owner_file, name: $prop_name})
MERGE (c)-[:HAS_PROP {required: $required}]->(p)
"""

LINK_OF_TYPE = """
MATCH (p:Prop  {owner: $owner, owner_file: $owner_file, name: $prop_name})
MATCH (t:Class {name: $type_name})
MERGE (p)-[:OF_TYPE]->(t)
"""

# Extended relationships
LINK_USES_BLOC = """
MATCH (screen:Class {name: $screen_name, file_path: $fp})
MATCH (bloc:Class   {name: $bloc_name})
MERGE (screen)-[:USES_BLOC]->(bloc)
"""

LINK_EMITS = """
MATCH (bloc:Class  {name: $bloc_name,  file_path: $fp})
MATCH (state:Class {name: $state_name})
MERGE (bloc)-[:EMITS]->(state)
"""

LINK_HANDLES = """
MATCH (bloc:Class  {name: $bloc_name,  file_path: $fp})
MATCH (event:Class {name: $event_name})
MERGE (bloc)-[:HANDLES]->(event)
"""

LINK_NAVIGATES_TO = """
MATCH (from_s:Class {name: $from_name, file_path: $fp})
MATCH (to_s:Class   {name: $to_name})
MERGE (from_s)-[:NAVIGATES_TO {route: $route}]->(to_s)
"""

LINK_CONTAINS = """
MATCH (parent:Class {name: $parent_name, file_path: $fp})
MATCH (child:Class  {name: $child_name,  file_path: $fp})
MERGE (parent)-[:CONTAINS]->(child)
"""


# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------

def ingest(lib_root: Path, memgraph_uri: str) -> None:
    dart_files = sorted(lib_root.rglob("*.dart"))
    if not dart_files:
        print(f"No .dart files found under {lib_root}", file=sys.stderr)
        sys.exit(1)

    print(f"Parsing {len(dart_files)} .dart files...")
    parsed      = [parse_dart_file(f, lib_root) for f in dart_files]
    known_paths = {p["path"] for p in parsed}

    # Build navigation resolution map: router_class_name → {const_name → target_class}
    # e.g. nav_resolution["AppRouter"]["home"] == "HomePage"
    nav_resolution: dict[str, dict[str, str]] = {}
    for pf in parsed:
        if pf["route_nav_map"]:
            for cls in pf["classes"]:
                if cls["role"] == "router":
                    nav_resolution[cls["name"]] = pf["route_nav_map"]

    print(f"Connecting to Memgraph at {memgraph_uri} ...")
    driver = GraphDatabase.driver(memgraph_uri, auth=("", ""))

    with driver.session() as session:
        for q in SCHEMA_QUERIES:
            try:
                session.run(q)
            except Exception:
                pass

        session.run(CLEAR_QUERY)
        print("Cleared existing AST nodes.")

        # ── Pass 1: File and Class nodes ──────────────────────────────────
        for pf in parsed:
            session.run(
                UPSERT_FILE,
                path=pf["path"], name=pf["name"],
                layer=pf["layer"], feature=pf["feature"], sublayer=pf["sublayer"],
            )
            for cls in pf["classes"]:
                session.run(
                    UPSERT_CLASS,
                    name=cls["name"], file_path=cls["file_path"],
                    kind=cls["kind"], is_abstract=cls["is_abstract"], role=cls["role"],
                )

        class_count = sum(len(p["classes"]) for p in parsed)
        print(f"Created {class_count} Class nodes across {len(parsed)} File nodes.")

        # ── Pass 2: Semantic multi-labels ─────────────────────────────────
        label_count = 0
        for pf in parsed:
            for cls in pf["classes"]:
                label = _ROLE_LABEL.get(cls["role"])
                if label:
                    session.run(
                        ADD_SEMANTIC_LABEL.format(label=label),
                        name=cls["name"], fp=cls["file_path"],
                    )
                    label_count += 1
        print(f"Applied {label_count} semantic labels.")

        # ── Pass 3: Relationships ─────────────────────────────────────────
        missing_imports = 0
        prop_count      = 0
        ec: dict[str, int] = {k: 0 for k in (
            "DEFINES", "IMPORTS", "EXTENDS", "IMPLEMENTS", "MIXES_IN",
            "DEPENDS_ON", "HAS_PROP", "OF_TYPE",
            "USES_BLOC", "EMITS", "HANDLES", "NAVIGATES_TO", "CONTAINS",
        )}

        for pf in parsed:
            # DEFINES
            for cls in pf["classes"]:
                session.run(LINK_DEFINES, file_path=pf["path"], class_name=cls["name"])
                ec["DEFINES"] += 1

            # IMPORTS (project-internal only)
            for imp in pf["imports"]:
                if imp in known_paths:
                    session.run(LINK_IMPORT, from_path=pf["path"], to_path=imp)
                    ec["IMPORTS"] += 1
                else:
                    missing_imports += 1

            # DEPENDS_ON (file-level final fields → any class in the file)
            for fd in pf["field_deps"]:
                session.run(LINK_DEPENDS_ON,
                            file_path=pf["path"],
                            dep_type=fd["type"], field=fd["field"])
                ec["DEPENDS_ON"] += 1

            # Per-class relationships
            class_names_in_file = {c["name"] for c in pf["classes"]}
            for cls in pf["classes"]:
                fp = cls["file_path"]

                if cls["extends"]:
                    session.run(LINK_EXTENDS,
                                child=cls["name"], child_path=fp, parent=cls["extends"])
                    ec["EXTENDS"] += 1

                for iface in cls["implements"]:
                    session.run(LINK_IMPLEMENTS,
                                child=cls["name"], child_path=fp, iface=iface)
                    ec["IMPLEMENTS"] += 1

                for mix in cls["with"]:
                    session.run(LINK_MIXES_IN,
                                child=cls["name"], child_path=fp, mix=mix)
                    ec["MIXES_IN"] += 1

                # Props → :Prop nodes + HAS_PROP + OF_TYPE
                for prop in cls["props"]:
                    session.run(UPSERT_PROP,
                                owner=cls["name"], owner_file=fp,
                                prop_name=prop["name"], prop_type=prop["type"],
                                required=prop["required"])
                    session.run(LINK_HAS_PROP,
                                owner=cls["name"], owner_file=fp,
                                prop_name=prop["name"], required=prop["required"])
                    session.run(LINK_OF_TYPE,
                                owner=cls["name"], owner_file=fp,
                                prop_name=prop["name"], type_name=prop["type"])
                    ec["HAS_PROP"] += 1
                    ec["OF_TYPE"]  += 1
                    prop_count     += 1

                # USES_BLOC — context.read/watch<XBloc>()
                for bloc_name in cls["uses_blocs"]:
                    session.run(LINK_USES_BLOC,
                                screen_name=cls["name"], fp=fp, bloc_name=bloc_name)
                    ec["USES_BLOC"] += 1

                # EMITS / HANDLES — Bloc<Event, State> generic params
                if cls["emits_state"]:
                    session.run(LINK_EMITS,
                                bloc_name=cls["name"], fp=fp,
                                state_name=cls["emits_state"])
                    ec["EMITS"] += 1
                if cls["handles_event"]:
                    session.run(LINK_HANDLES,
                                bloc_name=cls["name"], fp=fp,
                                event_name=cls["handles_event"])
                    ec["HANDLES"] += 1

                # NAVIGATES_TO — Navigator.push*Named(context, AppRouter.home)
                for nav_target in cls["nav_targets"]:
                    target_class = None
                    if "." in nav_target:
                        router_name, const_name = nav_target.rsplit(".", 1)
                        target_class = nav_resolution.get(router_name, {}).get(const_name)
                    if target_class:
                        session.run(LINK_NAVIGATES_TO,
                                    from_name=cls["name"], fp=fp,
                                    to_name=target_class, route=nav_target)
                        ec["NAVIGATES_TO"] += 1

                # CONTAINS — private _Widget instantiation in this class body
                for widget_name in cls["contains_widgets"]:
                    if widget_name in class_names_in_file and widget_name != cls["name"]:
                        session.run(LINK_CONTAINS,
                                    parent_name=cls["name"], fp=fp,
                                    child_name=widget_name)
                        ec["CONTAINS"] += 1

        if missing_imports:
            print(f"  ({missing_imports} external package imports skipped)")

        print(f"Created {prop_count} Prop nodes.")
        print("Edge counts:")
        for rel, cnt in ec.items():
            print(f"  {rel:15s}: {cnt}")

    driver.close()
    print("Ingestion complete.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--demo-app-path",
        default=os.environ.get(
            "DEMO_APP_PATH",
            str(Path(__file__).parent.parent / "demo_app" / "lib"),
        ),
    )
    parser.add_argument(
        "--memgraph-uri",
        default=os.environ.get("MEMGRAPH_URI", "bolt://localhost:7687"),
    )
    args = parser.parse_args()

    lib_root = Path(args.demo_app_path).resolve()
    if not lib_root.is_dir():
        print(f"Error: {lib_root} is not a directory", file=sys.stderr)
        sys.exit(1)

    ingest(lib_root, args.memgraph_uri)


if __name__ == "__main__":
    main()
