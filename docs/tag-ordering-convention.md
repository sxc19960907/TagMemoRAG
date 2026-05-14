# Tag Ordering Convention (manual.metadata.tags)

## TL;DR

When you author or edit a manual's metadata, write `tags` in **specific-to-broad** order. The first tag should be the narrowest concept that distinguishes this manual from siblings; later tags name larger categories the manual belongs to.

This document explains why the array order is meaningful and how the storage layer interprets it.

---

## Why the order matters

Phase 0 adds a SQLite table `manual_tags(kb_name, manual_id, tag_id, position INTEGER)` where `position` is the 1-indexed offset of the tag inside `metadata.tags`. The position field is **persisted** alongside the link.

Future search-side work (Wave Phase 1+) reads `position` to compute a sequence-aware co-occurrence weight, modeled after the source algorithm:

```
phi(pos, n) = 0.9 - 0.4 * (pos - 1) / max(n - 1, 1)
```

Earlier positions get higher weight. If your tags are written in arbitrary order, the weight signal is noise; if they're written specific-to-broad, the weight matches user intent (the most specific tag dominates ranking).

Phase 0 itself does **not** read `position` to influence retrieval results — `execute_search` output is byte-identical to before. The convention exists now so that:

1. Newly authored manuals immediately follow the right shape.
2. Phase 1+ can land without a separate metadata migration.

---

## How to order tags

Order from the narrowest, most specific concept to the broadest. Examples:

| Manual | Recommended `tags` order |
|---|---|
| Washer fault-code reference | `["fault-code", "diagnostics", "washer"]` |
| AC remote-control quick start | `["remote-control", "quick-start", "ac"]` |
| Dishwasher detergent guidance | `["detergent", "maintenance-task", "dishwasher"]` |

Heuristics:

- The first tag often names the **document's primary intent** (a fault-code reference, a quick-start, an FAQ).
- Middle tags name the **functional category** (diagnostics, maintenance-task, troubleshooting).
- Trailing tags name the **product or platform** (washer, ac, fridge).

If two tags feel equally specific, prefer the one a user is more likely to type as their search query first.

---

## What happens if I don't follow it?

- Phase 0: nothing user-visible. Embeddings, links, and EPA basis are computed regardless of order.
- Phase 1+: the sequence-aware co-occurrence weight will degrade — your manual will look "as if" all its tags were broad terms, and the system's ability to rank a specific-intent query above a broad-category query will drop.

There's no hard validation error. The `/manuals/validate` endpoint may emit a non-blocking `info` message reminding you of the convention.

---

## Notes for batch import / scripted authoring

- `manual_bulk_import` preserves `metadata.tags` order as-is. Write the array in the desired order at the source.
- Tag governance (rename / merge / delete) preserves the position of remaining tags; the position field is not re-derived from text.
- Synonym resolution maps each input tag to a canonical tag *before* writing `manual_tags` rows; positions are taken from the original input order.

---

## Schema reference

```sql
CREATE TABLE IF NOT EXISTS manual_tags (
    kb_name    TEXT NOT NULL,
    manual_id  TEXT NOT NULL,
    tag_id     INTEGER NOT NULL,
    position   INTEGER NOT NULL,
    PRIMARY KEY (kb_name, manual_id, tag_id),
    FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_manual_tags_tag ON manual_tags(tag_id);
CREATE INDEX IF NOT EXISTS idx_manual_tags_kb_manual ON manual_tags(kb_name, manual_id);
```

`position` is 1-indexed (matching the source data model) and unique within a `(kb_name, manual_id)` pair only by virtue of being filled from a list whose entries are de-duplicated upstream.
