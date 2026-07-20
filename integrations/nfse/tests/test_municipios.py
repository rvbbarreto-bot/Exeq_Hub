from django.core.cache import cache

from integrations.nfse.municipios import FocusMunicipioClient


def test_municipio_stub_and_cache():
    cache.clear()
    client = FocusMunicipioClient(mode="stub", token="x")
    first = client.get_municipio("3504107")
    second = client.get_municipio("3504107")
    assert first == second
    assert first["codigo_municipio"] == "3504107"
    exemplo = client.get_json_exemplo("3504107")
    assert exemplo["mode"] == "stub"
    overrides = client.suggested_overrides("3504107")
    assert isinstance(overrides, dict)
