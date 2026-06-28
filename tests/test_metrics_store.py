from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from open_alio_mcp import data_provider, metrics_store  # noqa: E402


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def test_finance_metrics_report_default_basis_without_alternatives() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        _write_json(
            base / "metrics" / "_index.json",
            {
                "categories": [
                    {
                        "category": "finance",
                        "label": "재무",
                        "unit": "백만원",
                        "years": ["2024"],
                        "org_count": 1,
                    }
                ]
            },
        )
        base_key = "요약 재무상태표(결산) | 고유사업 | 자산총계"
        _write_json(
            base / "metrics" / "finance.json",
            {
                "_meta": {
                    "category": "finance",
                    "label": "재무",
                    "unit": "백만원",
                    "years": ["2024"],
                    "caveats": [],
                },
                "orgs": {
                    "C0000": {
                        "name": "테스트기관",
                        "series": {base_key: {"2024": 100}},
                    }
                },
            },
        )
        _write_json(
            base / "canonical" / "metrics_v2" / "finance_context.json",
            {
                "_meta": {"category": "finance_context"},
                "orgs": {
                    "C0000": {
                        "name": "테스트기관",
                        "series": {
                            f"{base_key} | table=요약 재무상태표(K-IFRS)": {"2024": 100},
                            f"{base_key} | table=요약 재무상태표(K-GAAP)": {"2024": 200},
                        },
                    }
                },
            },
        )

        old_provider = data_provider.get_provider()
        data_provider.set_provider(data_provider.LocalDirProvider(base))
        metrics_store._cache.clear()
        metrics_store._optional_cache.clear()
        metrics_store._index = None
        try:
            result = metrics_store.get_metrics("C0000", "finance", item_query="자산총계")
            context_only = metrics_store.get_metrics("C0000", "finance", item_query="자산총계 K-GAAP")
        finally:
            data_provider.set_provider(old_provider)
            metrics_store._cache.clear()
            metrics_store._optional_cache.clear()
            metrics_store._index = None

        assert result["series"][base_key]["2024"] == 100
        assert "context_alternatives" not in result
        assert result["basis"]["mode"] == "default_series"
        assert result["basis"]["items"][base_key]["representative_context"] == "요약 재무상태표(K-IFRS)"
        assert result["basis"]["items"][base_key]["has_other_contexts"] is True

        assert context_only["found"] is True
        assert "context_alternatives" not in context_only
        assert context_only["basis"]["mode"] == "context_query"
        context_item = f"{base_key} | table=요약 재무상태표(K-GAAP)"
        assert context_only["series"][context_item]["2024"] == 200
        assert context_only["basis"]["items"][context_item]["context"] == "요약 재무상태표(K-GAAP)"
