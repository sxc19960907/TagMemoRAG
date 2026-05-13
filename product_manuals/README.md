# Product Manuals

Put source product manuals here for local KB builds.

PDF files are ignored by git. Use subdirectories per product, for example:

```text
product_manuals/fridge/fridge_gorenje.pdf
```

Add a sidecar metadata file next to each source manual:

```text
product_manuals/fridge/fridge_gorenje.pdf
product_manuals/fridge/fridge_gorenje.metadata.json
```

Template:

```json
{
  "manual_id": "gorenje-nrk6192-zh-cn-v1",
  "title": "Gorenje NRK6192 refrigerator manual",
  "source_file": "fridge_gorenje.pdf",
  "brand": "Gorenje",
  "product_category": "fridge",
  "product_name": "NRK6192",
  "product_model": "NRK6192",
  "language": "zh-CN",
  "version": "v1",
  "tags": ["temperature-setting", "maintenance", "troubleshooting"],
  "status": "active",
  "uploaded_at": "",
  "checksum": "",
  "notes": ""
}
```

Required fields are `manual_id`, `title`, `source_file`, `product_category`, and `language`. Tags are normalized to lower-kebab-case during build. Duplicate `manual_id` values in one KB build are rejected.

Build a KB from a product directory:

```bash
python -m tagmemorag build --docs product_manuals/fridge --kb fridge --config config.yaml
```

Search with metadata filters:

```bash
python -m tagmemorag search "冰箱温度怎么调" --kb fridge --category fridge --model NRK6192 --tag temperature-setting
```

## Managed Library Layout

The API-managed workflow stores manuals under `product_manuals/{kb_name}/` by default:

```text
product_manuals/default/coffee/cm1.md
product_manuals/default/coffee/cm1.metadata.json
product_manuals/default/.tagmemorag-library.json
product_manuals/default/.tagmemorag-tags.json
```

Use `POST /manuals/validate` to check metadata before writing, `POST /manuals` to upload a document plus sidecar metadata, and `GET /manual-library?kb_name=default` to list managed manuals. Uploads and metadata edits set a pending-change marker; they are not searchable until `POST /manual-library/rebuild` completes successfully.

Disable a manual by setting `status` to `disabled` through the API or sidecar. Disabled and archived manuals stay on disk for audit/recovery, remain visible in `GET /manual-library`, and are skipped by future builds. Hard delete removes both the source file and sidecar and is constrained to the configured library root.

## Tag Governance

Each managed KB can define canonical tags, synonyms, and deprecated tags in `.tagmemorag-tags.json`:

```json
{
  "schema_version": "1",
  "kb_name": "default",
  "policy_mode": "advisory",
  "canonical_tags": [
    {"tag": "maintenance", "label": "Maintenance", "description": "Cleaning and routine care"}
  ],
  "synonyms": {
    "cleaning": "maintenance",
    "clean": "maintenance"
  },
  "deprecated_tags": {
    "maintainance": {"replacement": "maintenance", "reason": "Misspelling"}
  }
}
```

Use `advisory` mode for warnings or `strict` mode to reject unknown/deprecated tags during validation and bulk preview. Synonyms still validate as warnings with their canonical replacement.

Tag workflow:

```bash
python -m tagmemorag tag stats --kb default
python -m tagmemorag tag rewrite-preview --kb default --source-tag cleaning --target-tag maintenance
python -m tagmemorag tag rewrite --kb default --source-tag cleaning --target-tag maintenance --update-policy
python -m tagmemorag tag policy --kb default --file tag-policy.json
```

Rewrite preview shows affected manuals and before/after tag sets without writing. Rewrite commit updates sidecars atomically, dedupes tags, can add source tags as policy aliases, and marks the KB pending rebuild. Rebuild after commit so the searchable graph matches the managed library.

Drift issues from `GET /manual-library/tags` mean sidecars use synonyms/deprecated/unknown tags, tags look like likely duplicates, or loaded graph tags differ from current sidecars.

## Bulk Import Metadata

Use `POST /manual-library/bulk/preview` before writing a batch. The preview detects unsafe paths, unsupported suffixes, missing file/metadata pairs, duplicate `manual_id`, duplicate `source_file`, and existing-library conflicts. Only rows without `severity=error` can be imported with `POST /manual-library/bulk/import`.

CSV template:

```csv
manual_id,title,source_file,brand,product_category,product_name,product_model,language,version,tags,status,notes
cm1,CM1 Manual,coffee/cm1.md,Acme,coffee,CM1,CM1,zh-CN,v1,"maintenance, steam-wand",active,
```

CSV tags are split on comma, semicolon, or newline, trimmed, and normalized to lower-kebab-case.

JSON example:

```json
[
  {
    "manual_id": "cm1",
    "title": "CM1 Manual",
    "source_file": "coffee/cm1.md",
    "product_category": "coffee",
    "language": "zh-CN",
    "tags": ["maintenance", "steam-wand"],
    "status": "active"
  }
]
```

JSONL uses one metadata object per line. Bulk modes are `create_only`, `upsert`, and `dry_run`; upsert requires explicit `overwrite=true`. A successful import writes source files plus sidecars under the managed library root and marks the KB pending rebuild.

CLI preview/import helpers use the same backend rules:

```bash
python -m tagmemorag manual-bulk preview --metadata manuals.csv --metadata-format csv --file product_manuals/default/coffee/cm1.md
python -m tagmemorag manual-bulk import --metadata manuals.csv --metadata-format csv --file product_manuals/default/coffee/cm1.md --selected-row 2
```
