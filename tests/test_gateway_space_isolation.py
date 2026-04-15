from core.governance import gateway as gateway_module
from core.governance.gateway import get_gateway, invalidate_gateway_cache
from services.knowledge import parameter_registry
from services.knowledge.parameter_registry import ParameterRegistry


def test_registry_per_space(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    responses = iter([
        '[{"value":"72500","type":"MTOW","unit":"kg","context":"A"}]',
        '[{"value":"65000","type":"MLW","unit":"kg","context":"B"}]',
    ])
    monkeypatch.setattr(
        parameter_registry,
        "call_local_llm",
        lambda system_prompt, user_query: next(responses),
    )

    registry_a = ParameterRegistry(space_id="space-a")
    registry_b = ParameterRegistry(space_id="space-b")

    assert registry_a.register_parameters("chunk-a", "MTOW 72500 kg", 1, "a.pdf") == 1
    assert registry_b.register_parameters("chunk-b", "MLW 65000 kg", 2, "b.pdf") == 1

    params_a = tmp_path / "data" / "spaces" / "space-a" / "params.json"
    params_b = tmp_path / "data" / "spaces" / "space-b" / "params.json"
    assert params_a.exists()
    assert params_b.exists()
    assert "72500" in params_a.read_text(encoding="utf-8")
    assert "65000" in params_b.read_text(encoding="utf-8")
    assert "65000" not in params_a.read_text(encoding="utf-8")


def test_gateway_per_space_cache(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    gateway_module._gateway_cache.clear()

    gateway_a = get_gateway("space-a")
    gateway_b = get_gateway("space-b")

    assert gateway_a is get_gateway("space-a")
    assert gateway_a is not gateway_b
    assert gateway_a._registry.registry_path.endswith("data/spaces/space-a/params.json")
    assert gateway_b._registry.registry_path.endswith("data/spaces/space-b/params.json")

    invalidate_gateway_cache("space-a")
    assert get_gateway("space-a") is not gateway_a


def test_cross_space_no_leak(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    gateway_module._gateway_cache.clear()

    registry_a = ParameterRegistry(space_id="space-a")
    registry_a.registry = {
        "chunk-a": {
            "72500": [
                {
                    "type": "MZFW",
                    "unit": "kg",
                    "source": "shared.pdf",
                    "page": 1,
                    "context": "conflicting type",
                }
            ]
        }
    }
    registry_a._save()

    response = "<citation src='shared.pdf' page='1'>MTOW is 72500 kg</citation>"
    contexts = [
        {
            "text": "MTOW is 72500 kg",
            "metadata": {
                "source": "shared.pdf",
                "page": "1",
                "bbox": [1, 2, 3, 4],
            },
        }
    ]

    is_valid_a, error_a, citations_a = get_gateway("space-a").validate_and_parse(
        response,
        contexts,
    )
    is_valid_b, safe_b, citations_b = get_gateway("space-b").validate_and_parse(
        response,
        contexts,
    )

    assert not is_valid_a
    assert "逻辑幻觉拦截" in error_a
    assert citations_a == []
    assert is_valid_b
    assert safe_b == response
    assert citations_b[0]["source_file"] == "shared.pdf"
