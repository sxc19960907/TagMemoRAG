# T9 Phase 8 connectors kickoff — Design

## Scope

Add a local connector foundation that transforms connector records into normal
manual-library source files and metadata sidecars. This preserves the existing
parser/chunker/index/retrieve contracts and avoids parallel ingestion logic.

## Module Layout

```text
src/tagmemorag/connectors/
  __init__.py
  base.py
  provider.py
  materialize.py
```

- `base.py`: dataclasses and `ConnectorProvider` protocol.
- `provider.py`: deterministic fixture provider and factory.
- `materialize.py`: safe file/metadata sidecar writer.
- `config.py`: `ConnectorsConfig`.

## Config

```yaml
connectors:
  enabled: false
  provider: fixture
  materialized_root_dir: data/connectors
  strict_sync: false
```

## Data Flow

1. Provider returns `ConnectorRecord`s.
2. Materializer validates safe source path and supported suffix.
3. Materializer writes content bytes and sidecar metadata into
   `{materialized_root_dir}/{kb_name}/`.
4. Caller can pass that directory to existing `build_kb()`.

## Safety

Summaries include counts, bounded failure reasons, provider name, and record ids.
They do not include content, secrets, or absolute paths.

## Tests

- Config defaults/override.
- Fixture provider create/tombstone records.
- Materializer writes markdown and metadata.
- Invalid suffix is summarized.
- Materialized docs are retrievable after `build_kb()`.
