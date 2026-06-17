# SKILLS.md — Flutter Developer Skills

This document defines the skills and responsibilities active in every session. All four skill areas apply together — they are not modes to switch between.

---

## 1. Clean Architecture

**Structure:** Feature-first. Every feature is self-contained under `lib/features/<feature>/` with three sub-layers: `domain`, `data`, `presentation`.

**Responsibilities:**
- Define domain entities as pure Dart classes with no framework dependencies.
- Write abstract repository contracts in the domain layer.
- Implement repository contracts in the data layer using models that extend entities.
- Create single-responsibility use cases that encapsulate one domain operation.
- Wire implementations via dependency injection (registered in `core/di/`).

**Layer dependency direction:**
```
presentation → domain ← data
```
Data and presentation both depend on domain. They never depend on each other.

**Key checks before adding a class:**
- Which layer does it belong to?
- Does it introduce a cross-layer dependency?
- Does a similar class already exist? (Query AST before creating.)

---

## 2. BLoC State Management

**Pattern:** `flutter_bloc`. One BLoC per feature (or logical sub-feature).

**Responsibilities:**
- Define events as immutable sealed/abstract classes with `const` constructors.
- Define states as sealed/abstract classes with concrete subclasses for each UI state (Initial, Loading, Loaded, Error).
- Implement the BLoC to call use cases via `on<Event>` handlers.
- Emit states to drive `BlocBuilder` for UI rebuilds.
- Use `BlocListener` for one-shot side effects (navigation, snackbars).
- Use `MultiBlocProvider` at the route level or feature root.

**Never:**
- Call a repository or data source directly from a BLoC.
- Hold mutable state outside of the emitted `State` objects.
- Forget to handle loading and error states — always emit them.

---

## 3. UI / Design System

**Source of truth:** `docs/DESIGN.md`

**Responsibilities:**
- Implement pixel-accurate layouts using the 12-column grid (80px columns, 16px gutters).
- Apply all colour, typography, spacing, radius, and elevation tokens from DESIGN.md.
- Build responsive layouts across three breakpoints: compact (mobile), medium (tablet), expanded (desktop).
- Use `Theme.of(context).colorScheme` and `Theme.of(context).textTheme` — never hardcode values.
- Use Poppins via `google_fonts` for all text.
- Use line-style icons only; minimum 48dp tap targets.
- Animate with the motion tokens from DESIGN.md; always respect `MediaQuery.disableAnimations`.

**Before any UI work:**
1. Read `docs/DESIGN.md`.
2. Identify the relevant design tokens (colour, spacing, type scale, radius).
3. Check `docs/CLAUDE.md` for enforced agent rules.

---

## 4. MCP / AST Querying

**Purpose:** Build semantic understanding of the codebase before making any code change. Prevents layer violations, duplicate logic, and broken imports.

**Available tools:**
| Tool | Use for |
|---|---|
| `mcp__postgres__ast_find` | Locate a class or file by name |
| `mcp__postgres__ast_dependencies` | See what a class depends on and what depends on it |
| `mcp__postgres__ast_query` | Run a custom Cypher query against the AST graph |
| `mcp__postgres__ast_feature_map` | Get a feature's full class inventory |
| `mcp__postgres__list_tables` | List PostgreSQL tables |
| `mcp__postgres__describe_table` | Inspect a table's columns |
| `mcp__postgres__query` | Run a raw SQL query |

**Standard pre-coding query sequence:**

```cypher
-- 1. Find the class
// mcp__postgres__ast_find(name: "ClassName")

-- 2. Inspect its properties and relationships
MATCH (c:Class {name: 'ClassName'})-[r]->(n)
RETURN type(r), n.name, n.type, labels(n)

-- 3. Check what depends on it
MATCH (f:File)-[:IMPORTS]->(t:File {name: 'file.dart'})
RETURN f.path

-- 4. Check inheritance
MATCH (c:Class {name: 'ClassName'})<-[r:EXTENDS|IMPLEMENTS]-(child)
RETURN type(r), child.name, child.file_path
```

**Graph schema quick reference:**
- Nodes: `Class`, `File`, `Prop`
- Relationships: `HAS_PROP`, `DEPENDS_ON`, `EXTENDS`, `IMPLEMENTS`, `IMPORTS`, `HAS_FIELD`
- Labels on Class nodes: `Entity`, `Model`, `Repository`, `UseCase`, `BlocClass`, `EventClass`, `StateClass`, `DataSource`, `Screen`, `Widget`
