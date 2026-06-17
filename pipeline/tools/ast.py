"""AST query tools — query the Memgraph code graph for demo_app architecture.

Graph schema populated by ingest_ast.py:

  Nodes
  -----
  (:File  {path, name, layer, feature, sublayer})
  (:Class {name, kind, role, is_abstract, file_path})
    + semantic multi-labels by role:
        :Screen       role=page
        :Widget       role=widget | widget_state
        :BlocClass    role=bloc | cubit
        :StateClass   role=state | state_base
        :EventClass   role=event | event_base
        :Entity       role=entity
        :Model        role=model
        :UseCase      role=usecase | usecase_base
        :Repository   role=repository | repository_impl
        :DataSource   role=datasource | datasource_impl
  (:Prop  {owner, owner_file, name, type, required})
    one node per constructor field declared on a widget/screen

  Relationships
  -------------
  (File)   -[:DEFINES]                    ->(Class)
  (File)   -[:IMPORTS]                    ->(File)
  (Class)  -[:EXTENDS]                    ->(Class)
  (Class)  -[:IMPLEMENTS]                 ->(Class)
  (Class)  -[:MIXES_IN]                   ->(Class)
  (Class)  -[:DEPENDS_ON {field}]         ->(Class)   final field injection
  (Class)  -[:HAS_PROP   {required}]      ->(Prop)    widget constructor field
  (Prop)   -[:OF_TYPE]                    ->(Class)   prop → its declared type
  (Screen|Widget) -[:USES_BLOC]           ->(BlocClass)   context.read/watch<X>()
  (BlocClass) -[:EMITS]                   ->(StateClass)  Bloc<E,S> generic param
  (BlocClass) -[:HANDLES]                 ->(EventClass)  Bloc<E,S> generic param
  (Screen) -[:NAVIGATES_TO {route}]       ->(Screen)  Navigator.push*Named()
  (Screen|Widget) -[:CONTAINS]            ->(Widget)  private _Widget instantiation

  Enum values for Class.role
  --------------------------
  bloc, cubit, event_base, event, state_base, state,
  repository, repository_impl, datasource, datasource_impl,
  usecase_base, usecase, entity, model, page, widget, widget_state,
  router, theme, enum, mixin, other

  Enum values for File.layer   : feature | core | root
  Enum values for File.sublayer: domain  | data | presentation
"""

from opentelemetry import trace

from _memgraph import cypher_query
from tools import tool


@tool
async def ast_query(cypher: str) -> list[dict]:
    """Run a freeform Cypher query against the AST graph in Memgraph.

    Use this for precise structural questions about the demo_app codebase.
    See the tool module docstring for the full graph schema.

    Example queries
    ---------------
    All BLoC classes:
      MATCH (c:Class {role: 'bloc'}) RETURN c.name, c.file_path

    Dependency chain from AuthBloc:
      MATCH (c:Class {name: 'AuthBloc'})-[:DEPENDS_ON*1..3]->(dep:Class)
      RETURN dep.name, dep.role

    Files that import auth_repository.dart:
      MATCH (f:File)-[:IMPORTS]->(t:File {name: 'auth_repository.dart'})
      RETURN f.path
    """
    span = trace.get_current_span()
    span.set_attribute("cypher.length", len(cypher))
    return await cypher_query(cypher)


@tool
async def ast_find(name: str) -> dict:
    """Find a class or file by name (case-insensitive, partial match).

    Returns matched nodes with their immediate relationships:
    extends, implements, mixins, direct dependencies, and defining file.

    Use this to quickly locate any class or file in demo_app and understand
    its place in the Clean Architecture hierarchy.
    """
    span = trace.get_current_span()
    span.set_attribute("search.name", name)

    raw_classes = await cypher_query(
        "MATCH (c:Class) WHERE toLower(c.name) CONTAINS toLower($name) "
        "RETURN c ORDER BY c.name LIMIT 10",
        {"name": name},
    )

    raw_files = await cypher_query(
        "MATCH (f:File) WHERE toLower(f.name) CONTAINS toLower($name) "
        "RETURN f ORDER BY f.path LIMIT 5",
        {"name": name},
    )

    enriched = []
    for row in raw_classes:
        c = row["c"]
        rels = await cypher_query(
            """
            MATCH (c:Class {name: $cname, file_path: $fpath})
            OPTIONAL MATCH (c)-[:EXTENDS]->(sup:Class)
            OPTIONAL MATCH (c)-[:IMPLEMENTS]->(iface:Class)
            OPTIONAL MATCH (c)-[:MIXES_IN]->(mix:Class)
            OPTIONAL MATCH (c)-[:DEPENDS_ON]->(dep:Class)
            OPTIONAL MATCH (f:File)-[:DEFINES]->(c)
            RETURN
              collect(DISTINCT sup.name)  AS extends,
              collect(DISTINCT iface.name) AS implements,
              collect(DISTINCT mix.name)  AS mixins,
              collect(DISTINCT dep.name)  AS depends_on,
              f.path AS file_path
            """,
            {"cname": c["name"], "fpath": c["file_path"]},
        )
        detail = rels[0] if rels else {}
        enriched.append({**c, **detail})

    span.set_attribute("search.classes_found", len(enriched))
    span.set_attribute("search.files_found", len(raw_files))
    return {"classes": enriched, "files": [r["f"] for r in raw_files]}


@tool
async def ast_dependencies(class_name: str, depth: int = 2) -> dict:
    """Return the dependency subgraph for a class.

    Reports:
    - depends_on : classes this class transitively depends on (downstream)
    - depended_by: classes that depend on this class (upstream)

    Traverses DEPENDS_ON, EXTENDS, and IMPLEMENTS edges up to `depth` hops
    (capped at 4).  Use this to understand coupling and layer compliance.
    """
    depth = max(1, min(depth, 4))
    span = trace.get_current_span()
    span.set_attribute("class_name", class_name)
    span.set_attribute("depth", depth)

    downstream = await cypher_query(
        f"""
        MATCH (c:Class {{name: $name}})
             -[:DEPENDS_ON|EXTENDS|IMPLEMENTS*1..{depth}]->
             (dep:Class)
        RETURN DISTINCT dep.name AS name, dep.role AS role, dep.file_path AS file_path
        ORDER BY dep.role, dep.name
        """,
        {"name": class_name},
    )

    upstream = await cypher_query(
        f"""
        MATCH (caller:Class)
             -[:DEPENDS_ON|EXTENDS|IMPLEMENTS*1..{depth}]->
             (c:Class {{name: $name}})
        RETURN DISTINCT caller.name AS name, caller.role AS role, caller.file_path AS file_path
        ORDER BY caller.role, caller.name
        """,
        {"name": class_name},
    )

    span.set_attribute("deps.downstream", len(downstream))
    span.set_attribute("deps.upstream", len(upstream))
    return {
        "class": class_name,
        "depth": depth,
        "depends_on": downstream,
        "depended_by": upstream,
    }


@tool
async def ast_feature_map(feature: str | None = None) -> list[dict]:
    """List files and classes organized by feature/layer.

    If `feature` is given (e.g. "auth", "candidates"), returns a per-file
    breakdown with sublayer and class list.

    If `feature` is None (default), returns a summary row per layer/feature
    with file_count and class_count.  Use this to understand the overall
    module structure and identify which features/layers exist.
    """
    span = trace.get_current_span()
    span.set_attribute("feature", feature or "all")

    if feature:
        rows = await cypher_query(
            """
            MATCH (f:File {feature: $feature})
            OPTIONAL MATCH (f)-[:DEFINES]->(c:Class)
            RETURN
              f.path     AS file,
              f.sublayer AS sublayer,
              collect({name: c.name, role: c.role, kind: c.kind, is_abstract: c.is_abstract})
                AS classes
            ORDER BY f.sublayer, f.path
            """,
            {"feature": feature},
        )
    else:
        rows = await cypher_query(
            """
            MATCH (f:File)
            OPTIONAL MATCH (f)-[:DEFINES]->(c:Class)
            RETURN
              f.layer   AS layer,
              f.feature AS feature,
              count(DISTINCT f) AS file_count,
              count(DISTINCT c) AS class_count
            ORDER BY layer, feature
            """
        )

    span.set_attribute("feature_map.rows", len(rows))
    return rows
