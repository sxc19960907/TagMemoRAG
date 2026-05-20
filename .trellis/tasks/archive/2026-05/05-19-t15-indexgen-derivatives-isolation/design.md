# T1.5 IndexGeneration derivatives isolation — Design

## Scope

T1.5 is a compatibility-first path isolation task. It does not migrate old data
or remove `_global`; it adds optional generation-aware path parameters so
generation builds can keep derivatives next to their core artifacts.

## Data Flow

- Legacy full/incremental rebuild calls stay unchanged.
- Generation/shadow code constructs `KbPaths(kb_name, cfg, generation=N)` and
  passes it into derivative builders.
- Builders write derivative files under `paths.generation_root`.
- Readers can be explicitly pointed at generation paths; legacy readers keep
  `_global` fallback.

## Files

- `epa_basis.py`: optional path override for basis/lock/dirty/retrain.
- `tag_cooccurrence.py`: optional generation path helper and load/save usage.
- `tag_rebuild.py`: optional `paths` parameter; writes cooccurrence to
  `paths.tag_cooccurrence` and uses that path for intrinsic residual training.
- `indexgen/shadow_build.py`: pass generation `KbPaths` into tag rebuild and EPA
  retrain if derivative rebuild is executed there.

## Compatibility

No caller is forced to adopt generation paths. Existing `_global` files and tests
remain valid.
