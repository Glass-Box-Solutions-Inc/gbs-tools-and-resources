"""Substrate bridge smoke tests — fail fast and loudly when the bridge breaks.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from conftest import requires_substrate
from wc_caseload_engine import substrate as bridge


@requires_substrate
def test_require_substrate_returns_root() -> None:
    root = bridge.require_substrate()
    assert root.is_dir()
    assert (root / "data" / "taxonomy.py").is_file()
    assert str(root) in sys.path


@requires_substrate
@pytest.mark.parametrize("module_name", bridge.REQUIRED_MODULES)
def test_every_required_substrate_module_imports(module_name: str) -> None:
    module = bridge.import_substrate(module_name)
    assert module.__name__ == module_name


@requires_substrate
def test_substrate_exposes_the_assets_phase_b_needs() -> None:
    taxonomy = bridge.import_substrate("data.taxonomy")
    lifecycle = bridge.import_substrate("data.lifecycle_engine")
    models = bridge.import_substrate("data.models")
    registry = bridge.import_substrate("pdf_templates.registry")
    base_template = bridge.import_substrate("pdf_templates.base_template")

    assert len(list(taxonomy.DocumentType)) == 15
    assert hasattr(lifecycle, "walk_lifecycle")
    assert hasattr(lifecycle, "collect_documents_for_case")
    assert hasattr(models, "GeneratedCase")
    assert registry.TEMPLATE_REGISTRY
    assert hasattr(base_template, "BaseTemplate")


@requires_substrate
def test_install_substrate_path_is_idempotent() -> None:
    first = bridge.install_substrate_path()
    before = sys.path.count(str(first))
    bridge.install_substrate_path()
    assert sys.path.count(str(first)) == before


def test_missing_substrate_raises_actionable_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bridge, "find_substrate", lambda: None)
    with pytest.raises(bridge.SubstrateUnavailableError) as excinfo:
        bridge.substrate_path()
    message = str(excinfo.value)
    assert bridge.SUBSTRATE_ENV_VAR in message
    assert "Searched:" in message
    assert "data/taxonomy.py" in message


def test_env_var_override_is_honoured(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = tmp_path / "merus-test-data-generator"
    (fake / "data").mkdir(parents=True)
    (fake / "pdf_templates").mkdir()
    (fake / "data" / "taxonomy.py").write_text("", encoding="utf-8")
    (fake / "data" / "lifecycle_engine.py").write_text("", encoding="utf-8")
    (fake / "pdf_templates" / "registry.py").write_text("", encoding="utf-8")

    monkeypatch.setenv(bridge.SUBSTRATE_ENV_VAR, str(fake))
    bridge.find_substrate.cache_clear()
    try:
        assert bridge.find_substrate() == fake.resolve()
    finally:
        bridge.find_substrate.cache_clear()


def test_no_substrate_module_was_copied_into_this_package() -> None:
    """ISC-72 anti-probe: the bridge imports, it never vendors."""
    package_dir = Path(bridge.__file__).resolve().parent
    for path in package_dir.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "class BaseTemplate" not in text
        assert "def walk_lifecycle" not in text
