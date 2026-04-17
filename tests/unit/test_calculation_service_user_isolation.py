import asyncio
import io
import json
from pathlib import Path

import pandas as pd
from fastapi import UploadFile

from api.services.calculation_service import CalculationService


COL_CLIENT = "\u6bcd\u516c\u53f8"
COL_MEDIA = "\u5a92\u4ecb"
COL_SERVICE_TYPE = "\u670d\u52a1\u7c7b\u578b"
COL_MANAGED_CONSUMPTION = "\u4ee3\u6295\u6d88\u8017"
COL_CURRENCY = "\u5e01\u79cd"


def _write_minimal_consumption_excel(path: Path) -> None:
    pd.DataFrame(
        [
            {
                COL_CLIENT: "Acme",
                COL_MEDIA: "Google",
                COL_SERVICE_TYPE: "\u4ee3\u6295",
                COL_MANAGED_CONSUMPTION: 1.0,
                COL_CURRENCY: "USD",
            }
        ]
    ).to_excel(path, index=False)


def test_latest_consumption_file_isolated_by_owner(monkeypatch, tmp_path):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    service = CalculationService()
    monkeypatch.setattr(service, "_get_upload_dir", lambda: upload_dir)

    alice_file = upload_dir / "alice_20260417100000000000_a.xlsx"
    bob_file = upload_dir / "bob_20260417100000000000_a.xlsx"
    _write_minimal_consumption_excel(alice_file)
    _write_minimal_consumption_excel(bob_file)

    service._record_latest_consumption(
        str(alice_file),
        "alice.xlsx",
        owner_username="alice",
    )
    service._record_latest_consumption(
        str(bob_file),
        "bob.xlsx",
        owner_username="bob",
    )

    alice_latest_path, alice_original = service.get_latest_consumption_file(owner_username="alice")
    bob_latest_path, bob_original = service.get_latest_consumption_file(owner_username="bob")

    assert Path(alice_latest_path) == alice_file
    assert Path(bob_latest_path) == bob_file
    assert alice_original == "alice.xlsx"
    assert bob_original == "bob.xlsx"


def test_save_uploaded_file_uses_namespaced_unique_storage_path(monkeypatch, tmp_path):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    service = CalculationService()
    monkeypatch.setattr(service, "_get_upload_dir", lambda: upload_dir)
    monkeypatch.setattr(service, "_validate_consumption_workbook", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(service, "_audit", lambda **_kwargs: None)

    path_alice = asyncio.run(
        service.save_uploaded_file(
            UploadFile(filename="consumption.xlsx", file=io.BytesIO(b"alice")),
            owner_username="alice",
        )
    )
    path_bob = asyncio.run(
        service.save_uploaded_file(
            UploadFile(filename="consumption.xlsx", file=io.BytesIO(b"bob")),
            owner_username="bob",
        )
    )

    alice_name = Path(path_alice).name
    bob_name = Path(path_bob).name
    assert alice_name != bob_name
    assert alice_name.startswith("alice_")
    assert bob_name.startswith("bob_")
    assert Path(path_alice).exists()
    assert Path(path_bob).exists()

    alice_meta = json.loads(service._get_latest_consumption_meta_path("alice").read_text(encoding="utf-8"))
    bob_meta = json.loads(service._get_latest_consumption_meta_path("bob").read_text(encoding="utf-8"))
    assert Path(str(alice_meta["file_path"])) == Path(path_alice).resolve()
    assert Path(str(bob_meta["file_path"])) == Path(path_bob).resolve()

