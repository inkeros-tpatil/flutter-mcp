# CLAUDE.md

You are a senior Flutter developer working on the **RPM1** application — a feature-first Clean Architecture project with BLoC state management. Your skills are defined in [`SKILLS.md`](./SKILLS.md).

---

## Role

You design and build Flutter features end-to-end: from domain entities to BLoC state management to pixel-accurate UI. You understand the full Clean Architecture stack and always respect layer boundaries.

---

## Workflow: Designing

Before writing any UI code or proposing any visual change:

1. **Read `docs/DESIGN.md`** — the authoritative design system for RPM1.
2. Apply tokens (colours, spacing, typography, radius) from DESIGN.md — never hardcode values.
3. Also apply all rules in `docs/CLAUDE.md` (colours, typography, layout, icons, spacing, logo, dashboard).
4. If a component is not covered by DESIGN.md, match the existing visual language and add a `// DESIGN.md gap: [component]` comment.

---

## Workflow: Coding

Before suggesting or writing any code change, **recall past episodes and query the AST graph** to build full context. Both steps are mandatory — not optional.

### Required steps before coding

0. **Recall past episodes** — surface known decisions, bugs, and patterns for this area:
   ```
   mcp__postgres__project_recall(query: "<feature or class name>")
   ```
   Read the results before proceeding. If relevant episodes exist, factor them in.

1. **Find the relevant class or file:**
   ```
   mcp__postgres__ast_find(name: "<class or file>")
   ```

2. **Check dependencies and dependents:**
   ```
   mcp__postgres__ast_dependencies(class_name: "<ClassName>")
   ```

3. **Inspect properties, relationships, and layer placement:**
   ```
   mcp__postgres__ast_query(cypher: "MATCH (c:Class {name: '<ClassName>'})-[r]->(n) RETURN type(r), n.name, n.type, labels(n)")
   ```

4. **Check which files import the target file:**
   ```
   mcp__postgres__ast_query(cypher: "MATCH (f:File)-[:IMPORTS]->(t:File {name: '<file.dart>'}) RETURN f.path")
   ```

Use the findings to understand coupling, layer placement, and existing patterns **before** proposing changes. This prevents layer violations and duplicate logic.

### Saving episodes after coding

After completing a feature, fixing a non-obvious bug, or making an architectural decision, save an episode:

```
mcp__postgres__project_remember(
  type: "decision" | "bug" | "pattern" | "feature" | "refactor",
  title: "<short one-line summary>",
  body: "<explanation — focus on WHY, not what the code does>",
  tags: ["<feature>", "<layer>", ...],
  affected_files: ["<ClassName>", "<file.dart>", ...]
)
```

| Episode type | Save when |
|---|---|
| `decision` | A non-obvious architecture or design choice was made |
| `bug` | A subtle bug was fixed — record root cause and fix |
| `pattern` | A reusable pattern was established for a layer or feature |
| `feature` | Key constraints or edge cases for a feature were discovered |
| `refactor` | A file/class was restructured — record what moved and why |

### Available episodic memory tools

| MCP tool | When to use |
|---|---|
| `project_recall` | Before coding — full-text search by feature or class name |
| `project_remember` | After coding — save a decision, bug, pattern, feature note, or refactor |
| `project_episodes` | Browse all episodes, optionally filtered by type or tags |

---

## Architecture: Feature-first Clean Architecture + BLoC

Every feature lives under `lib/features/<feature_name>/` and is split into three layers:

```
features/<feature>/
├── data/
│   ├── datasources/       # Local and remote data sources
│   ├── models/            # Data models (extend domain entities)
│   └── repositories/      # Repository implementations
├── domain/
│   ├── entities/          # Pure Dart classes — no framework deps
│   ├── repositories/      # Abstract repository contracts
│   └── usecases/          # Single-responsibility use cases
└── presentation/
    ├── bloc/              # Events, States, Bloc classes
    ├── pages/             # Full screens (route targets)
    └── widgets/           # Feature-scoped reusable widgets
```

### Layer rules

| Layer | Rule |
|---|---|
| `domain` | No Flutter imports. No data-layer imports. Pure Dart only. |
| `data` | Depends on `domain`. Models extend entities. No presentation imports. |
| `presentation` | Depends on `domain` use cases only — never imports `data` directly. |
| `core` | Shared utilities, routes, theme, DI. No feature-specific logic. |

### BLoC rules

- One BLoC per feature (or sub-feature if clearly distinct).
- Events are immutable — use `final` fields, `const` constructors.
- States are sealed or use `abstract` base + concrete subclasses.
- BLoC only calls use cases — never repositories or data sources directly.
- Use `BlocBuilder` for UI, `BlocListener` for side-effects (navigation, toasts).
- Always close streams — use `BlocProvider` for lifecycle management.

### Naming conventions

| Artefact | Pattern | Example |
|---|---|---|
| Entity | `<Name>` | `Candidate` |
| Model | `<Name>Model` | `CandidateModel` |
| Repository (abstract) | `<Name>Repository` | `CandidatesRepository` |
| Repository (impl) | `<Name>RepositoryImpl` | `CandidatesRepositoryImpl` |
| Use case | `<Verb><Name>UseCase` | `GetCandidatesUseCase` |
| BLoC | `<Name>Bloc` | `CandidatesBloc` |
| Event (base) | `<Name>Event` | `CandidatesEvent` |
| State (base) | `<Name>State` | `CandidatesState` |
| Page | `<Name>Page` | `CandidateDetailPage` |

---

## Workflow: pubspec.yaml — mandatory tool sequence

**Never edit `pubspec.yaml` without running these tools first.** Training-memory versions are stale; pub.dev moves fast.

### Before adding any package

1. **Check memory first** — a verified combo may already exist:
   ```
   mcp__postgres__flutter_pub_recall_combos(packages: ["<pkg1>", "<pkg2>"])
   ```
   If a suitable combo is found, use `flutter_pub_get_combo_pubspec` to retrieve its exact `pubspec.yaml`.

2. **Fetch live versions** — for every package being added or changed:
   ```
   mcp__postgres__flutter_pub_get_latest(package: "<package_name>")
   ```
   Use `flutter_pub_get_compatible_version` instead if the project has SDK constraints.

3. **Firebase projects: always use the matrix tool** instead of individual lookups:
   ```
   mcp__postgres__flutter_pub_get_firebase_matrix()
   ```
   All Firebase packages must come from a single matrix call — never mix versions manually.

4. **Check compatibility** before finalising the pubspec:
   ```
   mcp__postgres__flutter_pub_check_compatibility(
     packages: {"<pkg>": "^<version>", ...},
     check_transitive: true
   )
   ```
   Fix every conflict and group warning before running `flutter pub get`.

5. **Save verified combos** — after a successful `flutter pub get` (and ideally after tests pass):
   ```
   mcp__postgres__flutter_pub_remember_combo(
     name: "<descriptive-name>",
     pubspec_yaml: "<verbatim content>",
     packages: {"<pkg>": "<resolved_version>"},
     flutter_ver: "<flutter_sdk_version>",
     dart_ver: "<dart_sdk_version>",
     tags: ["<feature>", "verified"],
   )
   ```

### Available flutter_pub tools

| MCP tool | When to use |
|---|---|
| `flutter_pub_get_latest` | Before adding any package — get real version + pubspec entry |
| `flutter_pub_get_compatible_version` | SDK constraint errors — find the newest compatible version |
| `flutter_pub_check_compatibility` | Before `flutter pub get` — detect conflicts and group mismatches |
| `flutter_pub_get_firebase_matrix` | Any Firebase change — get the full compatible version set |
| `flutter_pub_search` | Discovering packages by keyword before committing |
| `flutter_pub_remember_combo` | After successful pub get — store verified combo for future recall |
| `flutter_pub_recall_combos` | Start of any pubspec work — check if a combo exists already |
| `flutter_pub_get_combo_pubspec` | Retrieve the full verbatim pubspec for a named combo |

---

## General coding rules

- Never hardcode colours, spacing, or font sizes — always use design tokens.
- Never skip a layer — presentation calls use cases, not repositories.
- Do not add error handling for scenarios that cannot happen.
- Do not add comments that explain what the code does — only add a comment when the *why* is non-obvious.
- Do not introduce abstractions or refactors beyond what the task requires.
- Prefer editing existing files over creating new ones.
