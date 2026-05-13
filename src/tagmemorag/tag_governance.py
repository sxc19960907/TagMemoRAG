from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Literal, Mapping, Sequence

from .config import Settings
from .errors import ErrorCode, ServiceError
from .manual_library import (
    ACTIVE_STATUSES,
    ManualLibraryRecord,
    ValidationMessage,
    library_root,
    list_records,
    mark_pending,
    metadata_to_dict,
    safe_source_path,
)
from .manuals import ManualMetadata, metadata_sidecar_path, normalize_tag
from .storage.atomic import atomic_write
from .types import GraphState

TAG_POLICY_NAME = ".tagmemorag-tags.json"
TAG_POLICY_SCHEMA_VERSION = "1"
PolicyMode = Literal["advisory", "strict"]
TagState = Literal["canonical", "synonym", "deprecated", "unknown"]
RewriteMode = Literal["merge", "rename"]


@dataclass(frozen=True)
class CanonicalTag:
    tag: str
    label: str = ""
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"tag": self.tag, "label": self.label, "description": self.description}


@dataclass(frozen=True)
class DeprecatedTag:
    tag: str
    replacement: str = ""
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"replacement": self.replacement, "reason": self.reason}


@dataclass(frozen=True)
class TagPolicy:
    kb_name: str
    schema_version: str = TAG_POLICY_SCHEMA_VERSION
    policy_mode: PolicyMode = "advisory"
    canonical_tags: tuple[CanonicalTag, ...] = ()
    synonyms: Mapping[str, str] = field(default_factory=dict)
    deprecated_tags: tuple[DeprecatedTag, ...] = ()
    updated_at: str = ""

    @property
    def configured(self) -> bool:
        return bool(self.canonical_tags or self.synonyms or self.deprecated_tags)

    @property
    def canonical_set(self) -> set[str]:
        return {item.tag for item in self.canonical_tags}

    @property
    def deprecated_map(self) -> dict[str, DeprecatedTag]:
        return {item.tag: item for item in self.deprecated_tags}

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "kb_name": self.kb_name,
            "policy_mode": self.policy_mode,
            "canonical_tags": [item.to_dict() for item in self.canonical_tags],
            "synonyms": dict(sorted(self.synonyms.items())),
            "deprecated_tags": {item.tag: item.to_dict() for item in self.deprecated_tags},
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class TagResolution:
    raw_tag: str
    tag: str
    canonical_tag: str
    state: TagState
    replacement: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw_tag": self.raw_tag,
            "tag": self.tag,
            "canonical_tag": self.canonical_tag,
            "state": self.state,
            "replacement": self.replacement,
        }


@dataclass(frozen=True)
class TagUsageStat:
    tag: str
    canonical_tag: str
    state: TagState
    manual_count: int
    active_manual_count: int
    inactive_manual_count: int
    graph_count: int
    examples: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "tag": self.tag,
            "canonical_tag": self.canonical_tag,
            "state": self.state,
            "manual_count": self.manual_count,
            "active_manual_count": self.active_manual_count,
            "inactive_manual_count": self.inactive_manual_count,
            "graph_count": self.graph_count,
            "examples": list(self.examples),
        }


@dataclass(frozen=True)
class TagDriftIssue:
    code: str
    severity: Literal["info", "warning", "error"]
    tag: str
    canonical_tag: str
    count: int
    manual_ids: tuple[str, ...] = ()
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "tag": self.tag,
            "canonical_tag": self.canonical_tag,
            "count": self.count,
            "manual_ids": list(self.manual_ids),
            "message": self.message,
        }


@dataclass(frozen=True)
class TagRewriteChange:
    manual_id: str
    source_file: str
    before_tags: tuple[str, ...]
    after_tags: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "manual_id": self.manual_id,
            "source_file": self.source_file,
            "before_tags": list(self.before_tags),
            "after_tags": list(self.after_tags),
        }


@dataclass(frozen=True)
class TagRewritePreview:
    kb_name: str
    mode: RewriteMode
    source_tags: tuple[str, ...]
    target_tag: str
    affected_count: int
    changes: tuple[TagRewriteChange, ...]
    issues: tuple[TagDriftIssue, ...] = ()
    rebuild_required: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "kb_name": self.kb_name,
            "mode": self.mode,
            "source_tags": list(self.source_tags),
            "target_tag": self.target_tag,
            "affected_count": self.affected_count,
            "changes": [item.to_dict() for item in self.changes],
            "issues": [item.to_dict() for item in self.issues],
            "rebuild_required": self.rebuild_required,
        }


@dataclass(frozen=True)
class TagRewriteResult:
    preview: TagRewritePreview
    updated_count: int
    skipped_count: int
    failures: tuple[dict[str, Any], ...] = ()
    policy: TagPolicy | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.preview.to_dict(),
            "updated_count": self.updated_count,
            "skipped_count": self.skipped_count,
            "failures": list(self.failures),
            "policy": self.policy.to_dict() if self.policy else None,
        }


def policy_path(kb_name: str, cfg: Settings) -> Path:
    root = library_root(kb_name, cfg)
    path = (root / TAG_POLICY_NAME).resolve()
    _ensure_under_root(path, root)
    return path


def load_tag_policy(kb_name: str, cfg: Settings) -> TagPolicy:
    path = policy_path(kb_name, cfg)
    if not path.exists():
        return TagPolicy(kb_name=kb_name)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ServiceError(
            ErrorCode.INVALID_INPUT,
            "Tag governance policy is not valid JSON.",
            {"kb_name": kb_name, "error": str(exc)},
        ) from exc
    return parse_tag_policy(data, kb_name=kb_name)


def save_tag_policy(kb_name: str, cfg: Settings, data: Mapping[str, Any] | TagPolicy) -> TagPolicy:
    policy = data if isinstance(data, TagPolicy) else parse_tag_policy(dict(data), kb_name=kb_name)
    updated = replace(policy, kb_name=kb_name, updated_at=_now())
    path = policy_path(kb_name, cfg)

    def write(tmp_path: Path) -> None:
        tmp_path.write_text(
            json.dumps(updated.to_dict(), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    atomic_write(path, write)
    return updated


def parse_tag_policy(data: Mapping[str, Any], *, kb_name: str) -> TagPolicy:
    if not isinstance(data, Mapping):
        raise _policy_error("Tag policy must be a JSON object.")
    mode = str(data.get("policy_mode") or "advisory").strip().lower()
    if mode not in {"advisory", "strict"}:
        raise _policy_error("policy_mode must be advisory or strict.", {"policy_mode": mode})
    canonical_tags = _parse_canonical_tags(data.get("canonical_tags", ()))
    canonical_set = {item.tag for item in canonical_tags}
    synonyms = _parse_synonyms(data.get("synonyms", {}))
    deprecated = _parse_deprecated(data.get("deprecated_tags", {}))
    policy = TagPolicy(
        kb_name=str(data.get("kb_name") or kb_name),
        schema_version=str(data.get("schema_version") or TAG_POLICY_SCHEMA_VERSION),
        policy_mode=mode,  # type: ignore[arg-type]
        canonical_tags=canonical_tags,
        synonyms=synonyms,
        deprecated_tags=deprecated,
        updated_at=str(data.get("updated_at") or ""),
    )
    _validate_policy(policy, canonical_set)
    return policy


def resolve_tag(raw_tag: str, policy: TagPolicy) -> TagResolution:
    tag = normalize_tag(str(raw_tag))
    if not tag:
        return TagResolution(raw_tag=str(raw_tag), tag="", canonical_tag="", state="unknown")
    canonical = policy.canonical_set
    if not policy.configured or not canonical:
        return TagResolution(raw_tag=str(raw_tag), tag=tag, canonical_tag=tag, state="canonical")
    if tag in canonical:
        return TagResolution(raw_tag=str(raw_tag), tag=tag, canonical_tag=tag, state="canonical")
    if tag in policy.synonyms:
        target = _resolve_mapping_target(tag, policy.synonyms, canonical)
        return TagResolution(raw_tag=str(raw_tag), tag=tag, canonical_tag=target, state="synonym", replacement=target)
    deprecated = policy.deprecated_map.get(tag)
    if deprecated is not None:
        replacement = deprecated.replacement
        canonical_tag = replacement or tag
        return TagResolution(
            raw_tag=str(raw_tag),
            tag=tag,
            canonical_tag=canonical_tag,
            state="deprecated",
            replacement=replacement,
        )
    return TagResolution(raw_tag=str(raw_tag), tag=tag, canonical_tag=tag, state="unknown")


def resolve_tags_for_search(tags: Sequence[str], policy: TagPolicy, *, include_original: bool = True) -> list[str]:
    resolved: set[str] = set()
    for tag in tags:
        normalized = normalize_tag(str(tag))
        if not normalized:
            continue
        resolution = resolve_tag(normalized, policy)
        resolved.add(resolution.canonical_tag or normalized)
        if include_original:
            resolved.add(normalized)
    return sorted(resolved)


def governance_validation_messages(tags: Sequence[str], policy: TagPolicy) -> tuple[ValidationMessage, ...]:
    if not policy.configured or not policy.canonical_tags:
        return ()
    messages: list[ValidationMessage] = []
    for tag in sorted({normalize_tag(str(item)) for item in tags if normalize_tag(str(item))}):
        resolution = resolve_tag(tag, policy)
        if resolution.state == "canonical":
            continue
        if resolution.state == "synonym":
            messages.append(
                ValidationMessage(
                    "tags",
                    "TAG_SYNONYM_USED",
                    "Tag is a synonym; use the canonical tag.",
                    {"tag": tag, "canonical_tag": resolution.canonical_tag, "severity": "warning"},
                )
            )
        elif resolution.state == "deprecated":
            severity = "error" if policy.policy_mode == "strict" else "warning"
            messages.append(
                ValidationMessage(
                    "tags",
                    "TAG_DEPRECATED",
                    "Tag is deprecated.",
                    {"tag": tag, "replacement": resolution.replacement, "severity": severity},
                )
            )
        elif resolution.state == "unknown":
            severity = "error" if policy.policy_mode == "strict" else "warning"
            messages.append(
                ValidationMessage(
                    "tags",
                    "TAG_UNKNOWN",
                    "Tag is not listed in the KB tag policy.",
                    {"tag": tag, "severity": severity},
                )
            )
    return tuple(messages)


def tag_usage_report(kb_name: str, cfg: Settings, *, graph_state: GraphState | None = None) -> dict[str, Any]:
    policy = load_tag_policy(kb_name, cfg)
    records = list_records(kb_name, cfg, graph_state=graph_state)
    stats = compute_tag_usage_stats(records, policy, graph_state=graph_state)
    issues = detect_tag_drift(stats, policy, graph_state=graph_state)
    return {
        "kb_name": kb_name,
        "policy": policy.to_dict(),
        "stats": [item.to_dict() for item in stats],
        "issues": [item.to_dict() for item in issues],
        "summary": {
            "tag_count": len(stats),
            "issue_count": len(issues),
            "error_count": sum(1 for issue in issues if issue.severity == "error"),
            "warning_count": sum(1 for issue in issues if issue.severity == "warning"),
        },
    }


def compute_tag_usage_stats(
    records: Sequence[ManualLibraryRecord],
    policy: TagPolicy,
    *,
    graph_state: GraphState | None = None,
    example_limit: int = 5,
) -> tuple[TagUsageStat, ...]:
    counts: dict[str, Counter[str]] = defaultdict(Counter)
    examples: dict[str, list[str]] = defaultdict(list)
    for record in records:
        tags = {normalize_tag(tag) for tag in record.metadata.tags if normalize_tag(tag)}
        for tag in tags:
            bucket = counts[tag]
            bucket["manual"] += 1
            if record.status in ACTIVE_STATUSES:
                bucket["active"] += 1
            else:
                bucket["inactive"] += 1
            if len(examples[tag]) < example_limit:
                examples[tag].append(record.manual_id)
    graph_counts = _graph_tag_counts(graph_state)
    for tag, graph_count in graph_counts.items():
        counts[tag]["graph"] = graph_count
    stats: list[TagUsageStat] = []
    for tag in sorted(counts):
        resolution = resolve_tag(tag, policy)
        stats.append(
            TagUsageStat(
                tag=tag,
                canonical_tag=resolution.canonical_tag or tag,
                state=resolution.state,
                manual_count=counts[tag]["manual"],
                active_manual_count=counts[tag]["active"],
                inactive_manual_count=counts[tag]["inactive"],
                graph_count=counts[tag]["graph"],
                examples=tuple(examples[tag]),
            )
        )
    return tuple(stats)


def detect_tag_drift(
    stats: Sequence[TagUsageStat],
    policy: TagPolicy,
    *,
    graph_state: GraphState | None = None,
) -> tuple[TagDriftIssue, ...]:
    issues: list[TagDriftIssue] = []
    by_tag = {stat.tag: stat for stat in stats}
    for stat in stats:
        if stat.manual_count:
            if stat.state == "unknown" and policy.configured and policy.canonical_tags:
                severity = "error" if policy.policy_mode == "strict" else "warning"
                issues.append(_issue("UNKNOWN_TAG", severity, stat, "Tag is not listed in the KB tag policy."))
            elif stat.state == "synonym":
                issues.append(_issue("SYNONYM_IN_USE", "warning", stat, "Sidecars use a synonym instead of its canonical tag."))
            elif stat.state == "deprecated":
                severity = "error" if policy.policy_mode == "strict" else "warning"
                issues.append(_issue("DEPRECATED_TAG_IN_USE", severity, stat, "Deprecated tag is still present in sidecars."))
        if graph_state is not None and stat.manual_count != stat.graph_count:
            issues.append(
                _issue(
                    "GRAPH_LIBRARY_TAG_DRIFT",
                    "warning",
                    stat,
                    "Loaded graph tag counts differ from managed library sidecars; rebuild may be required.",
                )
            )
    canonical = sorted(policy.canonical_set)
    for stat in stats:
        if stat.state == "unknown" and stat.manual_count and (near := _near_canonical(stat.tag, canonical)):
            issues.append(
                _issue(
                    "LIKELY_DUPLICATE_TAG",
                    "info",
                    replace(stat, canonical_tag=near),
                    "Tag looks similar to a canonical tag.",
                )
            )
    for tag, graph_count in _graph_tag_counts(graph_state).items():
        if tag not in by_tag:
            resolution = resolve_tag(tag, policy)
            issues.append(
                TagDriftIssue(
                    code="GRAPH_LIBRARY_TAG_DRIFT",
                    severity="warning",
                    tag=tag,
                    canonical_tag=resolution.canonical_tag or tag,
                    count=graph_count,
                    message="Loaded graph has a tag absent from current managed library sidecars.",
                )
            )
    return tuple(sorted(issues, key=lambda item: (item.severity, item.code, item.tag)))


def preview_tag_rewrite(
    kb_name: str,
    cfg: Settings,
    *,
    source_tags: Sequence[str],
    target_tag: str,
    mode: RewriteMode = "merge",
) -> TagRewritePreview:
    sources = tuple(sorted({normalize_tag(tag) for tag in source_tags if normalize_tag(tag)}))
    target = normalize_tag(target_tag)
    if not sources:
        raise ServiceError(ErrorCode.INVALID_INPUT, "source_tags must include at least one tag.")
    if not target:
        raise ServiceError(ErrorCode.INVALID_INPUT, "target_tag must not be empty.")
    if mode == "rename" and len(sources) != 1:
        raise ServiceError(ErrorCode.INVALID_INPUT, "rename mode requires exactly one source tag.")
    policy = load_tag_policy(kb_name, cfg)
    target_resolution = resolve_tag(target, policy)
    issues: list[TagDriftIssue] = []
    if target_resolution.state == "deprecated":
        issues.append(
            TagDriftIssue(
                code="TARGET_TAG_DEPRECATED",
                severity="error",
                tag=target,
                canonical_tag=target_resolution.canonical_tag,
                count=0,
                message="Rewrite target is deprecated.",
            )
        )
    changes: list[TagRewriteChange] = []
    for record in list_records(kb_name, cfg):
        before = tuple(dict.fromkeys(normalize_tag(tag) for tag in record.metadata.tags if normalize_tag(tag)))
        if not set(before).intersection(sources):
            continue
        after = tuple(tag for tag in before if tag not in sources)
        after = tuple(dict.fromkeys((*after, target)))
        if before != after:
            changes.append(
                TagRewriteChange(
                    manual_id=record.manual_id,
                    source_file=record.source_file,
                    before_tags=before,
                    after_tags=after,
                )
            )
    return TagRewritePreview(
        kb_name=kb_name,
        mode=mode,
        source_tags=sources,
        target_tag=target,
        affected_count=len(changes),
        changes=tuple(changes),
        issues=tuple(issues),
    )


def commit_tag_rewrite(
    kb_name: str,
    cfg: Settings,
    *,
    source_tags: Sequence[str],
    target_tag: str,
    mode: RewriteMode = "merge",
    update_policy: bool = False,
    policy_alias_mode: Literal["synonym", "deprecated"] | None = None,
) -> TagRewriteResult:
    preview = preview_tag_rewrite(kb_name, cfg, source_tags=source_tags, target_tag=target_tag, mode=mode)
    if any(issue.severity == "error" for issue in preview.issues):
        raise ServiceError(
            ErrorCode.INVALID_INPUT,
            "Tag rewrite preview has blocking issues.",
            {"issues": [issue.to_dict() for issue in preview.issues]},
        )
    changes = {change.manual_id: change for change in preview.changes}
    updated = 0
    failures: list[dict[str, Any]] = []
    for record in list_records(kb_name, cfg):
        change = changes.get(record.manual_id)
        if change is None:
            continue
        try:
            source_path = safe_source_path(kb_name, record.source_file, cfg)
            metadata = replace(record.metadata, tags=change.after_tags)
            _write_metadata(metadata_sidecar_path(source_path), metadata)
            updated += 1
        except ServiceError as exc:
            failures.append({"manual_id": record.manual_id, "code": exc.code.value, "message": exc.message, "detail": exc.detail})
        except OSError as exc:
            failures.append({"manual_id": record.manual_id, "code": "WRITE_FAILED", "message": str(exc), "detail": {}})
    policy = None
    if update_policy:
        policy = _policy_with_aliases(kb_name, cfg, preview, alias_mode=policy_alias_mode or ("synonym" if mode == "merge" else "deprecated"))
        save_tag_policy(kb_name, cfg, policy)
    if updated:
        mark_pending(kb_name, cfg, pending=True)
    return TagRewriteResult(
        preview=preview,
        updated_count=updated,
        skipped_count=max(0, preview.affected_count - updated),
        failures=tuple(failures),
        policy=policy,
    )


def _policy_with_aliases(
    kb_name: str,
    cfg: Settings,
    preview: TagRewritePreview,
    *,
    alias_mode: Literal["synonym", "deprecated"],
) -> TagPolicy:
    policy = load_tag_policy(kb_name, cfg)
    canonical = list(policy.canonical_tags)
    if preview.target_tag not in policy.canonical_set:
        canonical.append(CanonicalTag(tag=preview.target_tag, label=preview.target_tag))
    synonyms = dict(policy.synonyms)
    deprecated = policy.deprecated_map
    for tag in preview.source_tags:
        if tag == preview.target_tag:
            continue
        if alias_mode == "synonym":
            synonyms[tag] = preview.target_tag
            deprecated.pop(tag, None)
        else:
            deprecated[tag] = DeprecatedTag(tag=tag, replacement=preview.target_tag)
            synonyms.pop(tag, None)
    return parse_tag_policy(
        {
            **policy.to_dict(),
            "canonical_tags": [item.to_dict() for item in canonical],
            "synonyms": synonyms,
            "deprecated_tags": {tag: item.to_dict() for tag, item in deprecated.items()},
        },
        kb_name=kb_name,
    )


def _parse_canonical_tags(value: Any) -> tuple[CanonicalTag, ...]:
    if value in (None, ""):
        return ()
    if not isinstance(value, list):
        raise _policy_error("canonical_tags must be a list.")
    tags: dict[str, CanonicalTag] = {}
    for item in value:
        if isinstance(item, str):
            raw = item
            label = ""
            description = ""
        elif isinstance(item, Mapping):
            raw = str(item.get("tag") or "")
            label = str(item.get("label") or "")
            description = str(item.get("description") or "")
        else:
            raise _policy_error("canonical_tags entries must be strings or objects.")
        tag = normalize_tag(raw)
        if not tag:
            raise _policy_error("canonical tag must not be empty.")
        tags[tag] = CanonicalTag(tag=tag, label=label, description=description)
    return tuple(tags[tag] for tag in sorted(tags))


def _parse_synonyms(value: Any) -> dict[str, str]:
    if value in (None, ""):
        return {}
    if not isinstance(value, Mapping):
        raise _policy_error("synonyms must be an object.")
    synonyms: dict[str, str] = {}
    for raw_alias, raw_target in value.items():
        alias = normalize_tag(str(raw_alias))
        target = normalize_tag(str(raw_target))
        if not alias or not target:
            raise _policy_error("synonym aliases and targets must not be empty.")
        synonyms[alias] = target
    return dict(sorted(synonyms.items()))


def _parse_deprecated(value: Any) -> tuple[DeprecatedTag, ...]:
    if value in (None, ""):
        return ()
    entries: dict[str, DeprecatedTag] = {}
    if isinstance(value, list):
        iterable = ((item.get("tag") if isinstance(item, Mapping) else "", item) for item in value)
    elif isinstance(value, Mapping):
        iterable = value.items()
    else:
        raise _policy_error("deprecated_tags must be an object or list.")
    for raw_tag, raw_detail in iterable:
        tag = normalize_tag(str(raw_tag))
        if not tag:
            raise _policy_error("deprecated tag must not be empty.")
        if isinstance(raw_detail, Mapping):
            replacement = normalize_tag(str(raw_detail.get("replacement") or ""))
            reason = str(raw_detail.get("reason") or "")
        else:
            replacement = normalize_tag(str(raw_detail or ""))
            reason = ""
        entries[tag] = DeprecatedTag(tag=tag, replacement=replacement, reason=reason)
    return tuple(entries[tag] for tag in sorted(entries))


def _validate_policy(policy: TagPolicy, canonical_set: set[str]) -> None:
    if policy.synonyms and not canonical_set:
        raise _policy_error("synonyms require canonical_tags.")
    for alias, target in policy.synonyms.items():
        if alias in canonical_set:
            raise _policy_error("synonym alias must not also be canonical.", {"tag": alias})
        _resolve_mapping_target(alias, policy.synonyms, canonical_set)
        if target not in canonical_set and target not in policy.synonyms:
            raise _policy_error("synonym target must resolve to a canonical tag.", {"alias": alias, "target": target})
    deprecated = policy.deprecated_map
    for tag, item in deprecated.items():
        if tag in canonical_set:
            raise _policy_error("deprecated tag must not also be canonical.", {"tag": tag})
        if item.replacement and item.replacement not in canonical_set and item.replacement not in policy.synonyms:
            raise _policy_error("deprecated replacement must resolve to a canonical tag.", {"tag": tag, "replacement": item.replacement})
        if item.replacement in policy.synonyms:
            _resolve_mapping_target(item.replacement, policy.synonyms, canonical_set)


def _resolve_mapping_target(start: str, synonyms: Mapping[str, str], canonical_set: set[str]) -> str:
    seen: set[str] = set()
    current = start
    while current in synonyms:
        if current in seen:
            raise _policy_error("synonym cycle detected.", {"tag": current})
        seen.add(current)
        current = synonyms[current]
    if current not in canonical_set:
        raise _policy_error("synonym target must resolve to a canonical tag.", {"tag": start, "target": current})
    return current


def _graph_tag_counts(graph_state: GraphState | None) -> Counter[str]:
    counts: Counter[str] = Counter()
    if graph_state is None:
        return counts
    by_manual: dict[str, set[str]] = defaultdict(set)
    for _, node in graph_state.graph.nodes(data=True):
        metadata = node.get("metadata") if isinstance(node.get("metadata"), dict) else node
        manual_id = str(metadata.get("manual_id", ""))
        raw_tags = metadata.get("tags", [])
        if manual_id and isinstance(raw_tags, list):
            by_manual[manual_id].update(normalize_tag(str(tag)) for tag in raw_tags if normalize_tag(str(tag)))
    for tags in by_manual.values():
        counts.update(tags)
    return counts


def _near_canonical(tag: str, canonical_tags: Sequence[str]) -> str:
    for canonical in canonical_tags:
        if len(tag) >= 5 and len(canonical) >= 5 and (tag.startswith(canonical) or canonical.startswith(tag)):
            return canonical
        if len(tag) >= 5 and _edit_distance_at_most(tag, canonical, 2):
            return canonical
        tag_tokens = set(tag.split("-"))
        canonical_tokens = set(canonical.split("-"))
        if tag_tokens and canonical_tokens and len(tag_tokens & canonical_tokens) / len(tag_tokens | canonical_tokens) >= 0.8:
            return canonical
    return ""


def _edit_distance_at_most(left: str, right: str, limit: int) -> bool:
    if abs(len(left) - len(right)) > limit:
        return False
    previous = list(range(len(right) + 1))
    for i, left_ch in enumerate(left, 1):
        current = [i]
        row_min = i
        for j, right_ch in enumerate(right, 1):
            cost = 0 if left_ch == right_ch else 1
            value = min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost)
            current.append(value)
            row_min = min(row_min, value)
        if row_min > limit:
            return False
        previous = current
    return previous[-1] <= limit


def _issue(code: str, severity: Literal["info", "warning", "error"], stat: TagUsageStat, message: str) -> TagDriftIssue:
    return TagDriftIssue(
        code=code,
        severity=severity,
        tag=stat.tag,
        canonical_tag=stat.canonical_tag,
        count=stat.manual_count,
        manual_ids=stat.examples,
        message=message,
    )


def _write_metadata(path: Path, metadata: ManualMetadata) -> None:
    def write(tmp_path: Path) -> None:
        tmp_path.write_text(
            json.dumps(metadata_to_dict(metadata), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    atomic_write(path, write)


def _ensure_under_root(path: Path, root: Path) -> None:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise ServiceError(ErrorCode.INVALID_INPUT, "Path escapes manual library root.", {"path": str(path)}) from exc


def _policy_error(message: str, detail: dict[str, Any] | None = None) -> ServiceError:
    return ServiceError(ErrorCode.INVALID_INPUT, message, detail)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
