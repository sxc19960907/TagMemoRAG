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
```

Use `POST /manuals/validate` to check metadata before writing, `POST /manuals` to upload a document plus sidecar metadata, and `GET /manual-library?kb_name=default` to list managed manuals. Uploads and metadata edits set a pending-change marker; they are not searchable until `POST /manual-library/rebuild` completes successfully.

Disable a manual by setting `status` to `disabled` through the API or sidecar. Disabled and archived manuals stay on disk for audit/recovery, remain visible in `GET /manual-library`, and are skipped by future builds. Hard delete removes both the source file and sidecar and is constrained to the configured library root.
