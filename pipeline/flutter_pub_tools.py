"""Flutter pub.dev intelligence tools.

Provides 8 MCP tools that fetch live pub.dev data so Claude always suggests
compatible, up-to-date Flutter package versions — never training-memory guesses.

Integration (one line):
    from flutter_pub_tools import flutter_pub_mcp
    your_existing_mcp.mount("flutter_pub", flutter_pub_mcp)

After mounting, tools are exposed as:
  flutter_pub_get_latest               — latest version + pubspec entry
  flutter_pub_get_compatible_version   — newest version matching your SDK
  flutter_pub_check_compatibility      — conflict + group-violation checker
  flutter_pub_get_firebase_matrix      — full Firebase compatible version set
  flutter_pub_search                   — search pub.dev by keyword
  flutter_pub_remember_combo           — store a verified working pubspec combo
  flutter_pub_recall_combos            — query stored combos by package/tag/SDK
  flutter_pub_get_combo_pubspec        — retrieve verbatim pubspec.yaml by name
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

import httpx
from fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field

flutter_pub_mcp = FastMCP("flutter_pub")

# ──────────────────────────────────────────────────────────────────────────────
# Arize Phoenix tracing — optional; works standalone or mounted beside the
# Phoenix-wired postgres_mcp server (which has already set the global provider)
# ──────────────────────────────────────────────────────────────────────────────
try:
    from _tracing import tracer as _tracer, mark_span_error as _mark_span_error, trigger_alerts as _trigger_alerts  # noqa: E501
    _HAS_TRACER = True
except ImportError:
    _tracer = None  # type: ignore[assignment]
    _HAS_TRACER = False

    def _mark_span_error(span, exc: Exception) -> None:  # type: ignore[misc]
        pass

    def _trigger_alerts(span, exc: Exception) -> None:  # type: ignore[misc]
        pass


@contextmanager
def _span(name: str):
    """Yield an OTEL span or None when running without the tracer."""
    if _HAS_TRACER and _tracer is not None:
        with _tracer.start_as_current_span(name) as span:
            yield span
    else:
        yield None


# ──────────────────────────────────────────────────────────────────────────────
# pub.dev API constants
# ──────────────────────────────────────────────────────────────────────────────
_PUB_API = "https://pub.dev/api"
_HEADERS = {
    "Accept": "application/json",
    "User-Agent": "flutter-pub-mcp/1.0 (dart-pub-tool)",
}
_TIMEOUT = 20.0


def _api_error(e: Exception, context: str) -> str:
    if isinstance(e, httpx.HTTPStatusError):
        return f"HTTP {e.response.status_code} {context}: {e.response.text[:300]}"
    if isinstance(e, httpx.TimeoutException):
        return f"Timeout {context}"
    return f"Error {context}: {type(e).__name__}: {e}"


# ──────────────────────────────────────────────────────────────────────────────
# Package groups — members must share the same major version
# ──────────────────────────────────────────────────────────────────────────────
PACKAGE_GROUPS: dict[str, list[str]] = {
    "firebase": [
        "firebase_core", "firebase_auth", "cloud_firestore", "firebase_storage",
        "firebase_messaging", "firebase_analytics", "firebase_crashlytics",
        "firebase_remote_config", "firebase_database", "firebase_app_check",
        "firebase_performance", "firebase_in_app_messaging", "firebase_app_installations",
    ],
    "flutter_bloc": ["flutter_bloc", "bloc", "bloc_test", "replay_bloc", "hydrated_bloc"],
    "riverpod": [
        "flutter_riverpod", "riverpod", "hooks_riverpod",
        "riverpod_generator", "riverpod_annotation",
    ],
    "dio": ["dio", "retrofit", "dio_cache_interceptor"],
    "freezed": ["freezed", "freezed_annotation"],
    "json_serializable": ["json_serializable", "json_annotation"],
    "auto_route": ["auto_route", "auto_route_generator"],
    "get": ["get", "get_storage", "getx"],
}

_PKG_TO_GROUP: dict[str, str] = {
    pkg: group
    for group, pkgs in PACKAGE_GROUPS.items()
    for pkg in pkgs
}


# ──────────────────────────────────────────────────────────────────────────────
# Pydantic input models (v2, ConfigDict) — FastMCP derives the JSON schema
# from these; each tool function accepts the model's fields as top-level params.
# ──────────────────────────────────────────────────────────────────────────────

class GetLatestInput(BaseModel):
    model_config = ConfigDict(strict=False)
    package: str = Field(description="pub.dev package name, e.g. 'go_router'")
    include_dependencies: bool = Field(
        default=False,
        description="Include the package's direct dependencies in the response",
    )


class GetCompatibleVersionInput(BaseModel):
    model_config = ConfigDict(strict=False)
    package: str
    dart_sdk: str = Field(description="Project Dart SDK version, e.g. '3.2.0'")
    flutter_sdk: Optional[str] = Field(
        default=None, description="Optional Flutter SDK version, e.g. '3.16.0'"
    )


class CheckCompatibilityInput(BaseModel):
    model_config = ConfigDict(strict=False)
    packages: dict = Field(
        description="Mapping of package_name → version_constraint, e.g. {'dio': '^5.0.0'}"
    )
    check_transitive: bool = Field(
        default=True,
        description="Also resolve one layer of transitive dependencies",
    )


class GetFirebaseMatrixInput(BaseModel):
    model_config = ConfigDict(strict=False)
    firebase_core_version: Optional[str] = Field(
        default=None,
        description="Target firebase_core version. Omit to use the latest.",
    )


class SearchInput(BaseModel):
    model_config = ConfigDict(strict=False)
    query: str = Field(description="Search string, e.g. 'state management'")
    limit: int = Field(default=10, ge=1, le=20)


class RememberComboInput(BaseModel):
    model_config = ConfigDict(strict=False)
    name: str = Field(description="Unique identifier, e.g. 'firebase-v3-flutter3.24'")
    pubspec_yaml: str = Field(description="Verbatim pubspec.yaml content")
    packages: dict = Field(description="{'package_name': 'resolved_version'}")
    description: Optional[str] = None
    flutter_ver: Optional[str] = None
    dart_ver: Optional[str] = None
    tags: Optional[list] = None


class RecallCombosInput(BaseModel):
    model_config = ConfigDict(strict=False)
    packages: Optional[list] = Field(
        default=None,
        description="Return only combos containing ALL of these package names",
    )
    flutter_ver_prefix: Optional[str] = Field(
        default=None, description="Filter by Flutter version prefix, e.g. '3.16'"
    )
    tags: Optional[list] = Field(
        default=None, description="Filter to combos containing ALL of these tags"
    )
    limit: int = Field(default=5, ge=1, le=50)


class GetComboPubspecInput(BaseModel):
    model_config = ConfigDict(strict=False)
    combo_name: str = Field(description="Exact name used in remember_combo")


# ──────────────────────────────────────────────────────────────────────────────
# Version constraint parser — pure Python, no semver library
# Implements Dart pub's flavour of semver constraints.
# ──────────────────────────────────────────────────────────────────────────────

def _parse_version(v: str) -> tuple[int, int, int]:
    """Parse 'X.Y.Z+build-pre' → (X, Y, Z), ignoring build and pre-release."""
    v = v.split("+")[0].split("-")[0].strip()
    parts = v.split(".")
    try:
        return (
            int(parts[0]) if len(parts) > 0 else 0,
            int(parts[1]) if len(parts) > 1 else 0,
            int(parts[2]) if len(parts) > 2 else 0,
        )
    except (ValueError, IndexError):
        return (0, 0, 0)


def _expand_caret(v: str) -> tuple[str, str]:
    """Expand '^X.Y.Z' → (lower_bound_str, upper_bound_str) per Dart semver rules.

    ^1.2.3 → >=1.2.3 <2.0.0   (first non-zero is major)
    ^0.1.2 → >=0.1.2 <0.2.0   (first non-zero is minor)
    ^0.0.3 → >=0.0.3 <0.0.4   (both zero, bump patch)
    """
    major, minor, patch = _parse_version(v)
    if major != 0:
        return (f">={v}", f"<{major + 1}.0.0")
    if minor != 0:
        return (f">={v}", f"<0.{minor + 1}.0")
    return (f">={v}", f"<0.0.{patch + 1}")


def _parse_bounds(
    constraint: str,
) -> tuple[tuple[int, int, int] | None, bool, tuple[int, int, int] | None, bool]:
    """Parse a constraint string → (lower, lower_inclusive, upper, upper_inclusive).

    Handles: 'any', exact version, '>=X', '<X', '>=X <Y', '^X.Y.Z'.
    """
    c = constraint.strip()

    if not c or c == "any":
        return (None, True, None, True)

    if c.startswith("^"):
        lo_s, hi_s = _expand_caret(c[1:])
        return (_parse_version(lo_s[2:]), True, _parse_version(hi_s[1:]), False)

    # Compound: ">=X <Y", ">=X <=Y", etc.
    if " " in c:
        lower: tuple[int, int, int] | None = None
        upper: tuple[int, int, int] | None = None
        lower_inc = True
        upper_inc = False
        for part in c.split():
            part = part.strip()
            if part.startswith(">="):
                lower, lower_inc = _parse_version(part[2:]), True
            elif part.startswith(">"):
                lower, lower_inc = _parse_version(part[1:]), False
            elif part.startswith("<="):
                upper, upper_inc = _parse_version(part[2:]), True
            elif part.startswith("<"):
                upper, upper_inc = _parse_version(part[1:]), False
        return (lower, lower_inc, upper, upper_inc)

    if c.startswith(">="):
        return (_parse_version(c[2:]), True, None, True)
    if c.startswith(">"):
        return (_parse_version(c[1:]), False, None, True)
    if c.startswith("<="):
        return (None, True, _parse_version(c[2:]), True)
    if c.startswith("<"):
        return (None, True, _parse_version(c[1:]), False)

    # Exact version
    ver = _parse_version(c)
    return (ver, True, ver, True)


def _version_satisfies(version_str: str, constraint: str) -> bool:
    """Return True if version_str satisfies the given Dart pub constraint."""
    try:
        ver = _parse_version(version_str)
        lower, lower_inc, upper, upper_inc = _parse_bounds(constraint)

        if lower is not None:
            if lower_inc and ver < lower:
                return False
            if not lower_inc and ver <= lower:
                return False

        if upper is not None:
            if upper_inc and ver > upper:
                return False
            if not upper_inc and ver >= upper:
                return False

        return True
    except Exception:
        return True  # unparseable constraints are treated as satisfied


def _constraints_intersect(c1: str, c2: str) -> bool:
    """Return True if any version could simultaneously satisfy both constraints."""
    try:
        l1, li1, u1, ui1 = _parse_bounds(c1)
        l2, li2, u2, ui2 = _parse_bounds(c2)

        # Effective lower = max(l1, l2)
        if l1 is None and l2 is None:
            eff_l, eff_li = None, True
        elif l1 is None:
            eff_l, eff_li = l2, li2
        elif l2 is None:
            eff_l, eff_li = l1, li1
        elif l1 > l2:
            eff_l, eff_li = l1, li1
        elif l2 > l1:
            eff_l, eff_li = l2, li2
        else:
            eff_l, eff_li = l1, li1 and li2

        # Effective upper = min(u1, u2)
        if u1 is None and u2 is None:
            eff_u, eff_ui = None, True
        elif u1 is None:
            eff_u, eff_ui = u2, ui2
        elif u2 is None:
            eff_u, eff_ui = u1, ui1
        elif u1 < u2:
            eff_u, eff_ui = u1, ui1
        elif u2 < u1:
            eff_u, eff_ui = u2, ui2
        else:
            eff_u, eff_ui = u1, ui1 and ui2

        if eff_l is None or eff_u is None:
            return True

        if eff_l > eff_u:
            return False
        if eff_l == eff_u:
            return bool(eff_li and eff_ui)
        return True
    except Exception:
        return True  # parse errors are non-conflicting


# ──────────────────────────────────────────────────────────────────────────────
# SQLite episodic memory — auto-created next to this file
# ──────────────────────────────────────────────────────────────────────────────
MEMORY_DB: Path = Path(__file__).parent / "flutter_pub_memory.db"


def _init_db() -> None:
    conn = sqlite3.connect(MEMORY_DB)
    conn.executescript("""
        PRAGMA journal_mode=WAL;
        PRAGMA foreign_keys=ON;

        CREATE TABLE IF NOT EXISTS combos (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            name         TEXT    UNIQUE NOT NULL,
            pubspec_yaml TEXT    NOT NULL,
            description  TEXT,
            flutter_ver  TEXT,
            dart_ver     TEXT,
            tags         TEXT    NOT NULL DEFAULT '[]',
            created_at   TEXT    NOT NULL DEFAULT (datetime('now')),
            updated_at   TEXT    NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS combo_packages (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            combo_id     INTEGER NOT NULL REFERENCES combos(id) ON DELETE CASCADE,
            package_name TEXT    NOT NULL,
            version      TEXT    NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cp_package ON combo_packages(package_name);
        CREATE INDEX IF NOT EXISTS idx_cp_combo   ON combo_packages(combo_id);
    """)
    conn.commit()
    conn.close()


_init_db()


# ──────────────────────────────────────────────────────────────────────────────
# HTTP helpers
# ──────────────────────────────────────────────────────────────────────────────

async def _pub_get(path: str, params: dict | None = None) -> dict:
    async with httpx.AsyncClient(follow_redirects=True, timeout=_TIMEOUT) as client:
        resp = await client.get(f"{_PUB_API}{path}", headers=_HEADERS, params=params)
        resp.raise_for_status()
        return resp.json()


async def _package_data(package: str) -> dict:
    return await _pub_get(f"/packages/{package}")


def _pubspec_entry(package: str, version: str) -> str:
    return f"  {package}: ^{version}"


def _sort_versions(versions: list[dict]) -> list[dict]:
    """Sort version entries newest-first by parsed version tuple."""
    def _key(v: dict) -> tuple[int, int, int]:
        try:
            return _parse_version(v["version"])
        except Exception:
            return (0, 0, 0)

    return sorted(versions, key=_key, reverse=True)


def _latest_satisfying(versions: list[dict], constraint: str) -> dict | None:
    """Return the newest version entry whose version string satisfies constraint."""
    for entry in _sort_versions(versions):
        if _version_satisfies(entry["version"], constraint):
            return entry
    return None


# ──────────────────────────────────────────────────────────────────────────────
# Tool 1 — get_latest  (mounted as flutter_pub_get_latest)
# ──────────────────────────────────────────────────────────────────────────────

@flutter_pub_mcp.tool()
async def get_latest(package: str, include_dependencies: bool = False) -> dict:
    """Fetch the latest stable version of a pub.dev package.

    **Always call this before adding a package to pubspec.yaml.**
    Do not guess versions from training memory — pub.dev moves fast and
    stale versions break `flutter pub get`.

    Args:
        package: pub.dev package name (e.g. "go_router", "firebase_auth").
        include_dependencies: When True, include the package's direct
            dependencies so you can understand coupling and SDK requirements.

    Returns:
        latest_version       — e.g. "14.2.0"
        pubspec_entry        — ready-to-paste line, e.g. "  go_router: ^14.2.0"
        dart_sdk_constraint  — environment.sdk value from the pubspec
        flutter_sdk_constraint — environment.flutter value (if any)
        published            — ISO 8601 publish timestamp
        group                — package group name if applicable
        group_warning        — reminder that all group members share major version
        direct_dependencies  — {name: constraint} (only if include_dependencies=True)

    Example:
        get_latest("go_router")
        → {"latest_version": "14.2.0", "pubspec_entry": "  go_router: ^14.2.0", ...}

        get_latest("firebase_auth")
        → {"latest_version": "5.3.3", "group": "firebase",
           "group_warning": "All packages in 'firebase' must share the same major version..."}
    """
    _in = GetLatestInput(package=package, include_dependencies=include_dependencies)

    with _span("tool.flutter_pub_get_latest") as span:
        try:
            if span:
                span.set_attribute("package", _in.package)

            data = await _package_data(_in.package)
            latest = data["latest"]
            version: str = latest["version"]
            pubspec = latest.get("pubspec", {})
            env = pubspec.get("environment", {})

            if span:
                span.set_attribute("version", version)

            result: dict = {
                "package": _in.package,
                "latest_version": version,
                "pubspec_entry": _pubspec_entry(_in.package, version),
                "dart_sdk_constraint": env.get("sdk", "unknown"),
                "flutter_sdk_constraint": env.get("flutter"),
                "published": latest.get("published"),
            }

            group = _PKG_TO_GROUP.get(_in.package)
            if group:
                members = ", ".join(PACKAGE_GROUPS[group])
                result["group"] = group
                result["group_warning"] = (
                    f"Package belongs to the '{group}' group. "
                    f"All members must share the same major version: {members}"
                )

            if _in.include_dependencies:
                result["direct_dependencies"] = pubspec.get("dependencies", {})

            return result

        except Exception as exc:
            if span:
                _mark_span_error(span, exc)
                _trigger_alerts(span, exc)
            return {"error": _api_error(exc, f"fetching {package}")}


# ──────────────────────────────────────────────────────────────────────────────
# Tool 2 — get_compatible_version  (mounted as flutter_pub_get_compatible_version)
# ──────────────────────────────────────────────────────────────────────────────

@flutter_pub_mcp.tool()
async def get_compatible_version(
    package: str,
    dart_sdk: str,
    flutter_sdk: Optional[str] = None,
) -> dict:
    """Find the newest version of a package that satisfies the project's SDK constraints.

    Walks all published versions newest-first and returns the first one whose
    `environment.sdk` constraint is satisfied by dart_sdk. If flutter_sdk is
    provided, also checks `environment.flutter`.

    Use this when the latest version is too new for the project's Dart SDK,
    or when `flutter pub get` fails with an SDK constraint error.

    Args:
        package: pub.dev package name.
        dart_sdk: The project's Dart SDK version (e.g. "2.19.6", "3.2.0").
        flutter_sdk: Optional Flutter SDK version (e.g. "3.16.0").

    Returns:
        compatible_version   — the resolved version string
        pubspec_entry        — ready-to-paste line
        dart_sdk_constraint  — the package version's own sdk constraint
        flutter_sdk_constraint — the package version's flutter constraint (if any)

    Example:
        get_compatible_version("dio", dart_sdk="2.19.0")
        → {"compatible_version": "4.0.6", "pubspec_entry": "  dio: ^4.0.6",
           "dart_sdk_constraint": ">=2.17.0 <3.0.0"}
    """
    _in = GetCompatibleVersionInput(
        package=package, dart_sdk=dart_sdk, flutter_sdk=flutter_sdk
    )

    with _span("tool.flutter_pub_get_compatible_version") as span:
        try:
            if span:
                span.set_attribute("package", _in.package)
                span.set_attribute("dart_sdk", _in.dart_sdk)

            data = await _package_data(_in.package)

            for entry in _sort_versions(data.get("versions", [])):
                pubspec = entry.get("pubspec", {})
                env = pubspec.get("environment", {})
                sdk_c = env.get("sdk", "any")

                if not _version_satisfies(_in.dart_sdk, sdk_c):
                    continue

                flutter_c = env.get("flutter")
                if _in.flutter_sdk and flutter_c:
                    if not _version_satisfies(_in.flutter_sdk, flutter_c):
                        continue

                version_str: str = entry["version"]
                return {
                    "package": _in.package,
                    "compatible_version": version_str,
                    "pubspec_entry": _pubspec_entry(_in.package, version_str),
                    "dart_sdk_constraint": sdk_c,
                    "flutter_sdk_constraint": flutter_c,
                }

            return {
                "package": _in.package,
                "compatible_version": None,
                "error": (
                    f"No version of '{_in.package}' is compatible with "
                    f"Dart SDK {_in.dart_sdk}"
                    + (f" / Flutter {_in.flutter_sdk}" if _in.flutter_sdk else "")
                ),
            }

        except Exception as exc:
            if span:
                _mark_span_error(span, exc)
                _trigger_alerts(span, exc)
            return {"error": _api_error(exc, f"fetching versions of {package}")}


# ──────────────────────────────────────────────────────────────────────────────
# Tool 3 — check_compatibility  (mounted as flutter_pub_check_compatibility)
# ──────────────────────────────────────────────────────────────────────────────

@flutter_pub_mcp.tool()
async def check_compatibility(
    packages: dict,
    check_transitive: bool = True,
) -> dict:
    """Detect version conflicts and package-group violations across a set of packages.

    For each package, fetches the pubspec of the latest version satisfying the
    given constraint and extracts its direct dependencies. If check_transitive
    is True, also fetches one level of transitive dependencies (capped at 30
    packages to stay within pub.dev rate limits). Any shared dependency with
    non-intersecting version constraints is a conflict; any package-group
    members at mismatched major versions is a group violation.

    Run this on the full packages dict BEFORE running `flutter pub get`.

    Args:
        packages: Dict mapping package_name → version_constraint, e.g.
            {"firebase_core": "^3.6.0", "firebase_auth": "^5.3.3"}.
        check_transitive: Resolve one additional level of transitive deps
            (recommended; adds pub.dev API calls).

    Returns:
        status        — "ok" or "conflicts_found"
        conflicts     — list of {dep, constraint_a, package_a, constraint_b,
                        package_b, fix_hint}
        group_warnings — list of group major-version mismatch messages

    Example:
        check_compatibility({"firebase_core": "^3.0.0", "firebase_auth": "^4.0.0"})
        → {"status": "conflicts_found",
           "group_warnings": ["Group 'firebase' major-version mismatch: ..."]}
    """
    _in = CheckCompatibilityInput(packages=packages, check_transitive=check_transitive)

    with _span("tool.flutter_pub_check_compatibility") as span:
        try:
            if span:
                span.set_attribute("package_count", len(_in.packages))
                span.set_attribute("check_transitive", _in.check_transitive)

            # Fetch direct deps for each requested package
            async def _fetch_deps(pkg: str, constraint: str) -> tuple[str, dict]:
                try:
                    data = await _package_data(pkg)
                    entry = _latest_satisfying(data.get("versions", []), constraint)
                    if entry is None:
                        entry = data.get("latest", {})
                    pubspec = (entry or {}).get("pubspec", {})
                    return (pkg, pubspec.get("dependencies", {}))
                except Exception:
                    return (pkg, {})

            direct_results = await asyncio.gather(
                *[_fetch_deps(p, c) for p, c in _in.packages.items()]
            )

            # dep_name → [(constraint, source_package), ...]
            dep_map: dict[str, list[tuple[str, str]]] = {}
            direct_deps: dict[str, dict] = {}

            for pkg_name, deps in direct_results:
                direct_deps[pkg_name] = deps
                for dep_name, dep_c in deps.items():
                    if isinstance(dep_c, str):
                        dep_map.setdefault(dep_name, []).append((dep_c, pkg_name))

            # Optionally resolve one transitive level
            if _in.check_transitive:
                trans_candidates = {
                    dep: c
                    for deps in direct_deps.values()
                    for dep, c in deps.items()
                    if isinstance(c, str) and dep not in _in.packages
                }
                # Cap to 30 to avoid hammering pub.dev
                trans_tasks = [
                    _fetch_deps(dep, c)
                    for dep, c in list(trans_candidates.items())[:30]
                ]
                trans_results = await asyncio.gather(*trans_tasks)
                for t_pkg, t_deps in trans_results:
                    for td, tc in t_deps.items():
                        if isinstance(tc, str):
                            dep_map.setdefault(td, []).append((tc, f"{t_pkg}[transitive]"))

            # Find conflicts: pairs of constraints on the same dep that don't intersect
            conflicts: list[dict] = []
            for dep_name, constraint_list in dep_map.items():
                if len(constraint_list) < 2:
                    continue
                seen: set[tuple[int, int]] = set()
                for i in range(len(constraint_list)):
                    for j in range(i + 1, len(constraint_list)):
                        pair = (i, j)
                        if pair in seen:
                            continue
                        seen.add(pair)
                        ca, pa = constraint_list[i]
                        cb, pb = constraint_list[j]
                        if not _constraints_intersect(ca, cb):
                            conflicts.append({
                                "dep": dep_name,
                                "constraint_a": ca,
                                "package_a": pa,
                                "constraint_b": cb,
                                "package_b": pb,
                                "fix_hint": (
                                    f"Resolve '{dep_name}' to a version satisfying both "
                                    f"'{ca}' (required by {pa}) and '{cb}' (required by {pb}). "
                                    f"Add an explicit dependency_overrides entry if needed."
                                ),
                            })

            # Check group major-version violations
            group_warnings: list[str] = []
            group_members: dict[str, list[tuple[str, int]]] = {}

            for pkg, constraint in _in.packages.items():
                group = _PKG_TO_GROUP.get(pkg)
                if not group:
                    continue
                try:
                    lower, lower_inc, _, _ = _parse_bounds(constraint)
                    major = lower[0] if lower else None
                except Exception:
                    major = None

                if major is not None:
                    group_members.setdefault(group, []).append((pkg, major))

            for group, members in group_members.items():
                majors = {m for _, m in members}
                if len(majors) > 1:
                    detail = ", ".join(f"{p}@major={m}" for p, m in members)
                    group_warnings.append(
                        f"Group '{group}' major-version mismatch: {detail}. "
                        f"All members must share the same major version."
                    )

            if span:
                span.set_attribute("conflicts.count", len(conflicts))
                span.set_attribute("group_warnings.count", len(group_warnings))

            return {
                "status": "conflicts_found" if conflicts or group_warnings else "ok",
                "conflicts": conflicts,
                "group_warnings": group_warnings,
            }

        except Exception as exc:
            if span:
                _mark_span_error(span, exc)
                _trigger_alerts(span, exc)
            return {"error": _api_error(exc, "checking compatibility")}


# ──────────────────────────────────────────────────────────────────────────────
# Tool 4 — get_firebase_matrix  (mounted as flutter_pub_get_firebase_matrix)
# ──────────────────────────────────────────────────────────────────────────────

@flutter_pub_mcp.tool()
async def get_firebase_matrix(firebase_core_version: Optional[str] = None) -> dict:
    """Build a compatible version matrix for the entire Firebase Flutter ecosystem.

    For every package in the 'firebase' group, finds the latest version whose
    dependency constraint on firebase_core includes the specified core version.
    If firebase_core_version is omitted, the current latest is fetched first.

    **Always use this tool when adding or upgrading Firebase packages.**
    Never mix Firebase package versions manually — they must all be compatible
    with the same firebase_core version.

    Args:
        firebase_core_version: Target firebase_core version (e.g. "3.6.0").
            Omit to use the latest published version.

    Returns:
        core_version        — the resolved firebase_core version
        compatible_versions — {package_name: version} for all firebase packages
        pubspec_snippet     — multi-line block ready to paste into pubspec.yaml
        not_found           — packages with no compatible version (check pub.dev)

    Example:
        get_firebase_matrix()
        → {"core_version": "3.6.0",
           "compatible_versions": {"firebase_core": "3.6.0", "firebase_auth": "5.3.3", ...},
           "pubspec_snippet": "  firebase_core: ^3.6.0\n  firebase_auth: ^5.3.3\n..."}
    """
    _in = GetFirebaseMatrixInput(firebase_core_version=firebase_core_version)

    with _span("tool.flutter_pub_get_firebase_matrix") as span:
        try:
            # Resolve firebase_core version
            core_ver = _in.firebase_core_version
            if not core_ver:
                core_data = await _package_data("firebase_core")
                core_ver = core_data["latest"]["version"]

            if span:
                span.set_attribute("firebase_core_version", core_ver)

            async def _find_compatible(pkg: str) -> tuple[str, str | None]:
                if pkg == "firebase_core":
                    return (pkg, core_ver)
                try:
                    data = await _package_data(pkg)
                    for entry in _sort_versions(data.get("versions", [])):
                        pubspec = entry.get("pubspec", {})
                        core_c = pubspec.get("dependencies", {}).get("firebase_core")
                        if core_c and isinstance(core_c, str):
                            if _version_satisfies(core_ver, core_c):
                                return (pkg, entry["version"])
                    return (pkg, None)
                except Exception:
                    return (pkg, None)

            results = await asyncio.gather(
                *[_find_compatible(p) for p in PACKAGE_GROUPS["firebase"]]
            )

            compatible: dict[str, str] = {}
            not_found: list[str] = []
            for pkg, ver in results:
                if ver:
                    compatible[pkg] = ver
                else:
                    not_found.append(pkg)

            snippet = "\n".join(
                f"  {pkg}: ^{ver}" for pkg, ver in sorted(compatible.items())
            )

            return {
                "core_version": core_ver,
                "compatible_versions": compatible,
                "pubspec_snippet": snippet,
                "not_found": not_found,
            }

        except Exception as exc:
            if span:
                _mark_span_error(span, exc)
                _trigger_alerts(span, exc)
            return {"error": _api_error(exc, "building Firebase matrix")}


# ──────────────────────────────────────────────────────────────────────────────
# Tool 5 — search  (mounted as flutter_pub_search)
# ──────────────────────────────────────────────────────────────────────────────

@flutter_pub_mcp.tool()
async def search(query: str, limit: int = 10) -> list[dict]:
    """Search pub.dev for packages matching a keyword query.

    Returns the top N results enriched with version and SDK constraint data.
    Use this to discover packages before committing to one.

    Args:
        query: Search string (e.g. "navigation router", "http client", "state management").
        limit: Max results to return (1–20, default 10).

    Returns list of dicts, each with:
        name, version, description, dart_sdk, flutter_sdk, pub_url.

    Example:
        search("navigation router", limit=5)
        → [{"name": "go_router", "version": "14.2.0",
             "pub_url": "https://pub.dev/packages/go_router", ...}, ...]
    """
    _in = SearchInput(query=query, limit=limit)

    with _span("tool.flutter_pub_search") as span:
        try:
            if span:
                span.set_attribute("query", _in.query)
                span.set_attribute("limit", _in.limit)

            data = await _pub_get("/search", {"q": _in.query})
            names = [p["package"] for p in data.get("packages", [])[: _in.limit]]

            async def _enrich(name: str) -> dict:
                try:
                    pkg_data = await _package_data(name)
                    latest = pkg_data.get("latest", {})
                    pubspec = latest.get("pubspec", {})
                    env = pubspec.get("environment", {})
                    return {
                        "name": name,
                        "version": latest.get("version"),
                        "description": pubspec.get("description", ""),
                        "dart_sdk": env.get("sdk"),
                        "flutter_sdk": env.get("flutter"),
                        "pub_url": f"https://pub.dev/packages/{name}",
                    }
                except Exception:
                    return {"name": name, "error": "failed to fetch details"}

            results = list(await asyncio.gather(*[_enrich(n) for n in names]))
            if span:
                span.set_attribute("results.count", len(results))
            return results

        except Exception as exc:
            if span:
                _mark_span_error(span, exc)
                _trigger_alerts(span, exc)
            return [{"error": _api_error(exc, f"searching '{query}'")}]


# ──────────────────────────────────────────────────────────────────────────────
# Tool 6 — remember_combo  (mounted as flutter_pub_remember_combo)
# ──────────────────────────────────────────────────────────────────────────────

@flutter_pub_mcp.tool()
async def remember_combo(
    name: str,
    pubspec_yaml: str,
    packages: dict,
    description: Optional[str] = None,
    flutter_ver: Optional[str] = None,
    dart_ver: Optional[str] = None,
    tags: Optional[list] = None,
) -> dict:
    """Store a verified working pubspec combination in persistent local memory.

    Call this after a successful `flutter pub get` (and ideally after tests
    pass) to record the exact versions for future recall. Upserts on name
    conflict so re-running after an upgrade just refreshes the record.

    Args:
        name: Unique key for this combo (e.g. "firebase-v3-flutter3.24").
        pubspec_yaml: Verbatim pubspec.yaml content to store and retrieve later.
        packages: {package_name: resolved_version} used for indexed lookup,
            e.g. {"firebase_core": "3.6.0", "firebase_auth": "5.3.3"}.
        description: Human-readable purpose of this combo.
        flutter_ver: Flutter SDK version verified with (e.g. "3.24.0").
        dart_ver: Dart SDK version (e.g. "3.5.0").
        tags: List of labels for filtering (e.g. ["firebase", "production"]).

    Returns:
        stored (name), combo_id, package_count.

    Example:
        remember_combo(
            name="firebase-core-v3-flutter3.24",
            pubspec_yaml="name: my_app\n...",
            packages={"firebase_core": "3.6.0", "firebase_auth": "5.3.3"},
            tags=["firebase", "verified"],
            flutter_ver="3.24.0",
            dart_ver="3.5.0",
        )
    """
    _in = RememberComboInput(
        name=name, pubspec_yaml=pubspec_yaml, packages=packages,
        description=description, flutter_ver=flutter_ver,
        dart_ver=dart_ver, tags=tags,
    )

    with _span("tool.flutter_pub_remember_combo") as span:
        try:
            if span:
                span.set_attribute("combo_name", _in.name)

            tags_json = json.dumps(_in.tags or [])

            def _db_op() -> int:
                conn = sqlite3.connect(MEMORY_DB)
                try:
                    conn.execute("PRAGMA foreign_keys=ON")
                    cur = conn.cursor()

                    existing = cur.execute(
                        "SELECT id FROM combos WHERE name = ?", (_in.name,)
                    ).fetchone()

                    if existing:
                        combo_id: int = existing[0]
                        cur.execute(
                            """
                            UPDATE combos SET
                                pubspec_yaml = ?,
                                description  = ?,
                                flutter_ver  = ?,
                                dart_ver     = ?,
                                tags         = ?,
                                updated_at   = datetime('now')
                            WHERE id = ?
                            """,
                            (
                                _in.pubspec_yaml, _in.description, _in.flutter_ver,
                                _in.dart_ver, tags_json, combo_id,
                            ),
                        )
                    else:
                        cur.execute(
                            """
                            INSERT INTO combos
                                (name, pubspec_yaml, description, flutter_ver, dart_ver,
                                 tags, created_at, updated_at)
                            VALUES (?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
                            """,
                            (
                                _in.name, _in.pubspec_yaml, _in.description,
                                _in.flutter_ver, _in.dart_ver, tags_json,
                            ),
                        )
                        combo_id = cur.lastrowid  # type: ignore[assignment]

                    cur.execute("DELETE FROM combo_packages WHERE combo_id = ?", (combo_id,))
                    cur.executemany(
                        "INSERT INTO combo_packages (combo_id, package_name, version) VALUES (?, ?, ?)",
                        [(combo_id, pkg, ver) for pkg, ver in _in.packages.items()],
                    )
                    conn.commit()
                    return combo_id
                finally:
                    conn.close()

            combo_id = await asyncio.to_thread(_db_op)
            return {
                "stored": _in.name,
                "combo_id": combo_id,
                "package_count": len(_in.packages),
            }

        except Exception as exc:
            if span:
                _mark_span_error(span, exc)
                _trigger_alerts(span, exc)
            return {"error": f"Database error: {exc}"}


# ──────────────────────────────────────────────────────────────────────────────
# Tool 7 — recall_combos  (mounted as flutter_pub_recall_combos)
# ──────────────────────────────────────────────────────────────────────────────

@flutter_pub_mcp.tool()
async def recall_combos(
    packages: Optional[list] = None,
    flutter_ver_prefix: Optional[str] = None,
    tags: Optional[list] = None,
    limit: int = 5,
) -> list[dict]:
    """Retrieve stored pubspec combos matching optional filters.

    All filters are optional and combinable. Call this FIRST before fetching
    live data — a previously verified combo is the safest starting point.

    Args:
        packages: Return only combos that contain ALL listed package names
            (e.g. ["firebase_core", "firebase_auth"]).
        flutter_ver_prefix: Filter by Flutter version prefix
            (e.g. "3.16" matches "3.16.0" and "3.16.3").
        tags: Return only combos that contain ALL listed tags
            (e.g. ["firebase", "production"]).
        limit: Max combos to return (default 5).

    Returns list of dicts, each with:
        name, description, flutter_ver, dart_ver, tags,
        packages (dict), pubspec_snippet, updated_at.

    Example:
        recall_combos(packages=["firebase_core"], tags=["production"])
        → [{"name": "firebase-core-v3", "packages": {"firebase_core": "3.6.0", ...}, ...}]
    """
    _in = RecallCombosInput(
        packages=packages, flutter_ver_prefix=flutter_ver_prefix,
        tags=tags, limit=limit,
    )

    with _span("tool.flutter_pub_recall_combos") as span:
        try:
            if span and _in.packages:
                span.set_attribute("filter.packages", ",".join(_in.packages))

            def _db_op() -> list[dict]:
                conn = sqlite3.connect(MEMORY_DB)
                conn.row_factory = sqlite3.Row
                try:
                    sql_parts: list[str] = ["SELECT c.* FROM combos c"]
                    params: list = []

                    if _in.packages:
                        placeholders = ",".join(["?"] * len(_in.packages))
                        sql_parts.append(
                            f"""
                            JOIN (
                                SELECT combo_id
                                FROM combo_packages
                                WHERE package_name IN ({placeholders})
                                GROUP BY combo_id
                                HAVING COUNT(DISTINCT package_name) = ?
                            ) pkg_filter ON c.id = pkg_filter.combo_id
                            """
                        )
                        params.extend(_in.packages)
                        params.append(len(_in.packages))

                    where: list[str] = []

                    if _in.flutter_ver_prefix:
                        where.append("c.flutter_ver LIKE ?")
                        params.append(f"{_in.flutter_ver_prefix}%")

                    if _in.tags:
                        for tag in _in.tags:
                            where.append("c.tags LIKE ?")
                            params.append(f'%"{tag}"%')

                    if where:
                        sql_parts.append("WHERE " + " AND ".join(where))

                    sql_parts.append("ORDER BY c.updated_at DESC LIMIT ?")
                    params.append(_in.limit)

                    rows = conn.execute(" ".join(sql_parts), params).fetchall()

                    result: list[dict] = []
                    for row in rows:
                        combo = dict(row)
                        combo["tags"] = json.loads(combo.get("tags") or "[]")
                        pkgs = conn.execute(
                            "SELECT package_name, version FROM combo_packages WHERE combo_id = ?",
                            (combo["id"],),
                        ).fetchall()
                        combo["packages"] = {p["package_name"]: p["version"] for p in pkgs}
                        combo["pubspec_snippet"] = combo.pop("pubspec_yaml", "")
                        result.append(combo)

                    return result
                finally:
                    conn.close()

            return await asyncio.to_thread(_db_op)

        except Exception as exc:
            if span:
                _mark_span_error(span, exc)
                _trigger_alerts(span, exc)
            return [{"error": f"Database error: {exc}"}]


# ──────────────────────────────────────────────────────────────────────────────
# Tool 8 — get_combo_pubspec  (mounted as flutter_pub_get_combo_pubspec)
# ──────────────────────────────────────────────────────────────────────────────

@flutter_pub_mcp.tool()
async def get_combo_pubspec(combo_name: str) -> dict:
    """Return the full verbatim pubspec.yaml for a stored combo.

    After recall_combos identifies a suitable combo, call this to get the
    complete pubspec.yaml content ready to copy into the project.

    Args:
        combo_name: Exact name used when the combo was stored via remember_combo.

    Returns:
        combo_name, pubspec_yaml (full verbatim content).
        On miss: {"error": "No combo named '...' found"}.

    Example:
        get_combo_pubspec("firebase-core-v3-flutter3.24")
        → {"combo_name": "firebase-core-v3-flutter3.24",
           "pubspec_yaml": "name: my_app\nversion: 1.0.0+1\n..."}
    """
    _in = GetComboPubspecInput(combo_name=combo_name)

    with _span("tool.flutter_pub_get_combo_pubspec") as span:
        try:
            if span:
                span.set_attribute("combo_name", _in.combo_name)

            def _db_op() -> str | None:
                conn = sqlite3.connect(MEMORY_DB)
                try:
                    row = conn.execute(
                        "SELECT pubspec_yaml FROM combos WHERE name = ?",
                        (_in.combo_name,),
                    ).fetchone()
                    return row[0] if row else None
                finally:
                    conn.close()

            pubspec_yaml = await asyncio.to_thread(_db_op)

            if pubspec_yaml is None:
                return {
                    "error": (
                        f"No combo named '{_in.combo_name}' found. "
                        "Use recall_combos() to list available combos."
                    )
                }

            return {"combo_name": _in.combo_name, "pubspec_yaml": pubspec_yaml}

        except Exception as exc:
            if span:
                _mark_span_error(span, exc)
                _trigger_alerts(span, exc)
            return {"error": f"Database error: {exc}"}


# ──────────────────────────────────────────────────────────────────────────────
# Standalone entry-point and self-tests
# ──────────────────────────────────────────────────────────────────────────────

def _run_tests() -> None:
    """Assert all version-constraint parser invariants. Raises AssertionError on failure."""

    # _parse_version
    assert _parse_version("1.2.3") == (1, 2, 3)
    assert _parse_version("1.2.3+4") == (1, 2, 3)
    assert _parse_version("1.2.3-beta") == (1, 2, 3)
    assert _parse_version("1.2.3+4-beta") == (1, 2, 3)
    assert _parse_version("0.1.2") == (0, 1, 2)
    assert _parse_version("0.0.3") == (0, 0, 3)
    assert _parse_version("10.0.0") == (10, 0, 0)

    # _expand_caret
    assert _expand_caret("1.2.3") == (">=1.2.3", "<2.0.0"), "major non-zero"
    assert _expand_caret("0.1.2") == (">=0.1.2", "<0.2.0"), "minor non-zero"
    assert _expand_caret("0.0.3") == (">=0.0.3", "<0.0.4"), "both zero"
    assert _expand_caret("2.0.0") == (">=2.0.0", "<3.0.0")
    assert _expand_caret("0.14.0") == (">=0.14.0", "<0.15.0")

    # _version_satisfies
    assert _version_satisfies("1.5.0", "^1.2.0"), "caret, in range"
    assert not _version_satisfies("2.0.0", "^1.2.0"), "caret, above upper"
    assert not _version_satisfies("1.0.0", "^1.2.0"), "caret, below lower"
    assert _version_satisfies("1.2.0", ">=1.2.0 <2.0.0"), "compound lower boundary"
    assert _version_satisfies("1.9.9", ">=1.2.0 <2.0.0"), "compound inner"
    assert not _version_satisfies("2.0.0", ">=1.2.0 <2.0.0"), "compound upper exclusive"
    assert _version_satisfies("3.0.0", "any"), "any"
    assert _version_satisfies("0.0.1", "any"), "any zero"
    assert _version_satisfies("1.0.0", "1.0.0"), "exact match"
    assert not _version_satisfies("1.0.1", "1.0.0"), "exact non-match"
    assert _version_satisfies("1.0.0", ">=1.0.0"), "lower bound only, equal"
    assert _version_satisfies("2.0.0", ">=1.0.0"), "lower bound only, above"
    assert not _version_satisfies("0.9.0", ">=1.0.0"), "lower bound only, below"
    assert _version_satisfies("0.9.0", "<1.0.0"), "upper bound only, below"
    assert not _version_satisfies("1.0.0", "<1.0.0"), "upper bound exclusive, equal"

    # _constraints_intersect
    assert _constraints_intersect("^1.0.0", "^1.2.0"), "both ^1.x"
    assert not _constraints_intersect("^1.0.0", "^2.0.0"), "^1 vs ^2"
    assert _constraints_intersect(">=1.0.0 <2.0.0", ">=1.5.0 <3.0.0"), "overlapping ranges"
    assert not _constraints_intersect(">=1.0.0 <1.5.0", ">=1.5.0 <2.0.0"), "touching but not overlapping"  # noqa: E501
    assert not _constraints_intersect("<1.0.0", ">=1.0.0"), "adjacent ranges, exclusive boundary"
    assert _constraints_intersect("any", "^1.0.0"), "any always intersects"
    assert _constraints_intersect("^1.0.0", "any"), "any always intersects reversed"
    assert _constraints_intersect("1.0.0", "1.0.0"), "same exact version"
    assert not _constraints_intersect("1.0.0", "1.0.1"), "different exact versions"

    # SQLite memory round-trip — build the schema directly in a temp file
    import tempfile
    import os

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        conn = sqlite3.connect(tmp_path)
        conn.execute("PRAGMA foreign_keys=ON")
        # Bootstrap the schema (mirrors _init_db)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS combos (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                name         TEXT    UNIQUE NOT NULL,
                pubspec_yaml TEXT    NOT NULL,
                description  TEXT,
                flutter_ver  TEXT,
                dart_ver     TEXT,
                tags         TEXT    NOT NULL DEFAULT '[]',
                created_at   TEXT    NOT NULL DEFAULT (datetime('now')),
                updated_at   TEXT    NOT NULL DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS combo_packages (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                combo_id     INTEGER NOT NULL REFERENCES combos(id) ON DELETE CASCADE,
                package_name TEXT    NOT NULL,
                version      TEXT    NOT NULL
            );
        """)

        tags_json = json.dumps(["firebase", "test"])
        conn.execute(
            "INSERT INTO combos (name, pubspec_yaml, tags, created_at, updated_at)"
            " VALUES (?,?,?,datetime('now'),datetime('now'))",
            ("test-combo", "name: test\n", tags_json),
        )
        combo_id: int = conn.execute(
            "SELECT id FROM combos WHERE name='test-combo'"
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO combo_packages (combo_id, package_name, version) VALUES (?,?,?)",
            (combo_id, "firebase_core", "3.6.0"),
        )
        conn.commit()

        # Store a second combo with a different package to test empty-result path
        conn.execute(
            "INSERT INTO combos (name, pubspec_yaml, tags, created_at, updated_at)"
            " VALUES (?,?,?,datetime('now'),datetime('now'))",
            ("other-combo", "name: other\n", json.dumps(["riverpod"])),
        )
        other_id: int = conn.execute(
            "SELECT id FROM combos WHERE name='other-combo'"
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO combo_packages (combo_id, package_name, version) VALUES (?,?,?)",
            (other_id, "riverpod", "2.5.1"),
        )
        conn.commit()

        # Recall by package name
        row = conn.execute(
            """
            SELECT c.name FROM combos c
            JOIN (
                SELECT combo_id FROM combo_packages
                WHERE package_name IN ('firebase_core')
                GROUP BY combo_id HAVING COUNT(DISTINCT package_name) = 1
            ) f ON c.id = f.combo_id
            """
        ).fetchone()
        assert row is not None and row[0] == "test-combo", "recall by package failed"

        # Recall by tag
        row2 = conn.execute(
            "SELECT name FROM combos WHERE tags LIKE '%\"firebase\"%'"
        ).fetchone()
        assert row2 is not None and row2[0] == "test-combo", "recall by tag failed"

        # Empty result for package not in any combo
        empty = conn.execute(
            """
            SELECT c.name FROM combos c
            JOIN (
                SELECT combo_id FROM combo_packages
                WHERE package_name IN ('nonexistent_pkg')
                GROUP BY combo_id HAVING COUNT(DISTINCT package_name) = 1
            ) f ON c.id = f.combo_id
            """
        ).fetchone()
        assert empty is None, "expected empty result for nonexistent package"

        # Verbatim pubspec round-trip
        pubspec_row = conn.execute(
            "SELECT pubspec_yaml FROM combos WHERE name='test-combo'"
        ).fetchone()
        assert pubspec_row[0] == "name: test\n", "verbatim pubspec mismatch"

    finally:
        conn.close()
        os.unlink(tmp_path)

    print("All version constraint and SQLite memory tests passed.")


if __name__ == "__main__":
    import sys

    if "--test" in sys.argv:
        _run_tests()
        sys.exit(0)

    if "--help" in sys.argv:
        print(__doc__)
        print("\nRun as MCP server (stdio):  python flutter_pub_tools.py")
        print("Run self-tests:              python flutter_pub_tools.py --test")
        sys.exit(0)

    # Always run tests before serving to surface regressions immediately
    _run_tests()
    flutter_pub_mcp.run()
