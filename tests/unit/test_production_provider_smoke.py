from __future__ import annotations

import json

from tagmemorag.production_provider_smoke import (
    ProductionProviderSmokeReport,
    ProviderSmokeStage,
    _metadata_for_manuals,
    _summarize_answer_payload,
    write_provider_smoke_report,
)


def test_smoke_report_serializes_without_raw_answer_text(tmp_path):
    report = ProductionProviderSmokeReport(
        status="passed",
        config_path="cfg.yaml",
        kb_name="default",
        workdir=str(tmp_path),
        stages=[
            ProviderSmokeStage(
                "answer_smoke",
                "passed",
                {
                    "answer_kind": "answer",
                    "answer_text_length": 42,
                    "answer_citation_count": 2,
                },
            )
        ],
        next_steps=["retain report"],
    )

    body = report.to_dict()
    assert body["schema_version"] == "production_provider_smoke.v1"
    assert "raw answer body" not in json.dumps(body)
    assert "answer_text_length" in json.dumps(body)
    assert "retain report" in report.to_markdown()

    output = tmp_path / "report.json"
    write_provider_smoke_report(report, output, fmt="json")
    assert json.loads(output.read_text(encoding="utf-8"))["status"] == "passed"


def test_metadata_for_manuals_discovers_sidecars_and_drops_checksum(tmp_path):
    manual = tmp_path / "washer.pdf"
    manual.write_bytes(b"%PDF")
    sidecar = tmp_path / "washer.metadata.json"
    sidecar.write_text(
        json.dumps(
            {
                "manual_id": "washer-1",
                "title": "Washer",
                "source_file": "old/path.pdf",
                "product_category": "washing_machine",
                "language": "zh-CN",
                "checksum": "raw-checksum",
                "tags": ["drain"],
            }
        ),
        encoding="utf-8",
    )

    metadata_text, metadata_format, metadata_source = _metadata_for_manuals(
        [manual],
        metadata_path=None,
        metadata_format="json",
        workdir=tmp_path,
    )

    rows = json.loads(metadata_text)
    assert metadata_format == "json"
    assert metadata_source.endswith("manual-metadata.generated.json")
    assert rows[0]["source_file"] == "washer.pdf"
    assert "checksum" not in rows[0]


def test_summarize_answer_payload_keeps_counts_not_text():
    payload = {
        "schema_version": "answer.v1",
        "kb_name": "default",
        "build_id": "b1",
        "plan_id": "p1",
        "answer": {
            "kind": "answer",
            "model_id": "deepseek-v4-flash",
            "text": "这是不应该进入报告的回答正文。",
            "citations": [{"citation_id": "cit_001"}],
        },
        "warnings": ["answer_warn"],
        "retrieve": {
            "results": [{"text": "检索片段也不应该进入报告。"}],
            "citations": [{"citation_id": "cit_001"}, {"citation_id": "cit_002"}],
            "answerability": {"answerable": True},
        },
    }

    summary = _summarize_answer_payload(payload)

    assert summary["answer_model_id"] == "deepseek-v4-flash"
    assert summary["answer_text_length"] == len("这是不应该进入报告的回答正文。")
    assert summary["answer_citation_count"] == 1
    assert summary["retrieve_result_count"] == 1
    assert summary["retrieve_citation_count"] == 2
    assert "text" not in summary
    assert "这是" not in json.dumps(summary, ensure_ascii=False)
