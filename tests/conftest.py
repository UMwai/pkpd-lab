import pytest


@pytest.fixture(autouse=True)
def isolated_lab_storage(monkeypatch, tmp_path):
    monkeypatch.setenv("PKPD_LAB_DATA_DIR", str(tmp_path / "labs"))
