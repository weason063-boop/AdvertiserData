from __future__ import annotations

import json
import logging
import re
import shutil
import threading
import time
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import HTTPException, UploadFile
from sqlalchemy.exc import OperationalError

from api.database import record_operation_audit, upsert_billing_history, upsert_client_stats_batch
from api.services.daily_fx_snapshot_service import DailyFxSnapshotService
from calculate_service_fee import calculate_service_fees

logger = logging.getLogger(__name__)


def secure_filename(filename: str) -> str:
    """Sanitize filename to prevent path traversal and unsafe chars."""
    if not filename:
        return "uploaded_file"
    filename = Path(filename).name
    filename = re.sub(r"[^\w.\-\u4e00-\u9fff]", "_", filename)
    if not filename or filename.strip() == ".":
        return "uploaded_file"
    return filename


class CalculationService:
    _MONTH_PATTERN = re.compile(r"^(20\d{2})-(0[1-9]|1[0-2])$")
    _RESULT_FILE_PATTERN = re.compile(r"^[\w.\-\u4e00-\u9fff]+_results\.xlsx$", re.IGNORECASE)
    _RESULT_ID_PATTERN = re.compile(r"^[a-f0-9]{32}$", re.IGNORECASE)
    _ALLOWED_EXCEL_EXTENSIONS = {".xlsx", ".xls"}

    def __init__(self, daily_fx_snapshot_service: DailyFxSnapshotService | None = None):
        self._daily_fx_snapshot_service = daily_fx_snapshot_service or DailyFxSnapshotService()
        self._result_registry_lock = threading.Lock()

    def _audit(
        self,
        *,
        action: str,
        actor: str,
        status: str,
        input_file: str | None = None,
        output_file: str | None = None,
        result_ref: str | None = None,
        error_message: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        record_operation_audit(
            category="billing",
            action=action,
            actor=actor,
            status=status,
            input_file=input_file,
            output_file=output_file,
            result_ref=result_ref,
            error_message=error_message,
            metadata=metadata,
        )

    def _get_upload_dir(self) -> Path:
        upload_dir = Path(__file__).parent.parent.parent / "uploads"
        upload_dir.mkdir(exist_ok=True)
        return upload_dir

    def _get_latest_consumption_meta_path(self) -> Path:
        return self._get_upload_dir() / ".latest_consumption.json"

    def _get_result_registry_path(self) -> Path:
        return self._get_upload_dir() / ".result_registry.json"

    def _validate_excel_extension(self, filename: str, *, context: str) -> None:
        suffix = Path(str(filename or "")).suffix.lower()
        if suffix not in self._ALLOWED_EXCEL_EXTENSIONS:
            allowed = ", ".join(sorted(self._ALLOWED_EXCEL_EXTENSIONS))
            raise HTTPException(status_code=400, detail=f"{context}仅支持 {allowed} 文件")

    def _open_excel_workbook(self, file_path: str, *, context: str) -> pd.ExcelFile:
        try:
            return pd.ExcelFile(file_path)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"{context}无法读取为 Excel: {exc}") from exc

    def _validate_consumption_workbook(self, file_path: str, original_filename: str) -> None:
        workbook = self._open_excel_workbook(file_path, context="消耗上传文件")
        try:
            valid_sheets = []
            missing_service_type = []
            missing_currency = []
            has_month_column = False
            has_consumption_column = False

            for sheet in workbook.sheet_names:
                header_df = pd.read_excel(workbook, sheet_name=sheet, nrows=0)
                cols = set(header_df.columns.tolist())
                if not {"母公司", "媒介"}.issubset(cols):
                    continue

                if "服务类型" not in cols:
                    missing_service_type.append(sheet)
                    continue

                valid_sheets.append(sheet)
                if "月份归属" in cols:
                    has_month_column = True
                if "代投消耗" in cols or "流水消耗" in cols:
                    has_consumption_column = True

                sheet_currency = self._normalize_sheet_currency(sheet)
                if sheet_currency == "OTHER" and "币种" not in cols:
                    missing_currency.append(sheet)
                if sheet_currency is None and "币种" not in cols:
                    missing_currency.append(sheet)

            if missing_service_type:
                hint = "、".join(missing_service_type[:3])
                raise HTTPException(status_code=400, detail=f"模板缺少必需列“服务类型”，问题 Sheet: {hint}")

            if missing_currency:
                hint = "、".join(missing_currency[:3])
                raise HTTPException(status_code=400, detail=f"模板缺少必需列“币种”，问题 Sheet: {hint}")

            if not valid_sheets:
                raise HTTPException(
                    status_code=400,
                    detail="未找到有效消耗数据 Sheet（至少包含 母公司/媒介/服务类型 列）",
                )

            if not has_consumption_column:
                raise HTTPException(status_code=400, detail="模板缺少“代投消耗”或“流水消耗”列")

            if not has_month_column and not self._parse_month_from_filename(original_filename):
                raise HTTPException(
                    status_code=400,
                    detail="缺少月份信息：请在文件名中携带 YYYY-MM，或在表格中提供“月份归属”列",
                )
        finally:
            workbook.close()

    def _validate_contract_workbook(self, file_path: str) -> None:
        workbook = self._open_excel_workbook(file_path, context="合同上传文件")
        try:
            if not workbook.sheet_names:
                raise HTTPException(status_code=400, detail="合同模板为空，未检测到任何 Sheet")

            sample_df = pd.read_excel(workbook, sheet_name=workbook.sheet_names[0], nrows=0)
            columns = [str(col).strip() for col in sample_df.columns]
            normalized = [col.replace(" ", "").lower() for col in columns]

            has_client_col = any(
                ("客户" in col and ("简称" in col or "名称" in col)) or col in {"name", "client"}
                for col in normalized
            )
            has_fee_col = any(("服务费" in col) or ("fee" in col) for col in normalized)

            if not has_client_col:
                raise HTTPException(status_code=400, detail="合同模板缺少必需列：客户简称/客户名称")
            if not has_fee_col:
                raise HTTPException(status_code=400, detail="合同模板缺少必需列：服务费")
        finally:
            workbook.close()

    def _default_result_registry(self) -> dict[str, Any]:
        return {"records": []}

    def _load_result_registry_unlocked(self) -> dict[str, Any]:
        path = self._get_result_registry_path()
        if not path.exists():
            return self._default_result_registry()
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            logger.warning("读取结果注册表失败，回退为空", exc_info=True)
            return self._default_result_registry()

        records = payload.get("records", []) if isinstance(payload, dict) else []
        normalized_records = []
        for item in records:
            if not isinstance(item, dict):
                continue
            result_id = str(item.get("id") or "").strip().lower()
            owner = str(item.get("owner") or "").strip()
            filename = secure_filename(str(item.get("filename") or ""))
            if not self._RESULT_ID_PATTERN.match(result_id):
                continue
            if not owner or not self._is_allowed_result_filename(filename):
                continue
            normalized_records.append(
                {
                    "id": result_id,
                    "owner": owner,
                    "filename": filename,
                    "source_file": str(item.get("source_file") or ""),
                    "operation": str(item.get("operation") or "calculate"),
                    "created_at": str(item.get("created_at") or datetime.utcnow().isoformat()),
                }
            )
        return {"records": normalized_records}

    def _save_result_registry_unlocked(self, state: dict[str, Any]) -> None:
        path = self._get_result_registry_path()
        tmp_path = path.with_suffix(f"{path.suffix}.{uuid.uuid4().hex}.tmp")
        serialized = json.dumps(state, ensure_ascii=False, indent=2)
        tmp_path.write_text(serialized, encoding="utf-8")
        try:
            tmp_path.replace(path)
            return
        except PermissionError:
            logger.warning("Atomic replace for result registry failed, fallback to direct write", exc_info=True)
        try:
            path.write_text(serialized, encoding="utf-8")
        finally:
            if tmp_path.exists():
                try:
                    tmp_path.unlink(missing_ok=True)
                except PermissionError:
                    logger.warning("Failed to cleanup result registry temp file: %s", tmp_path, exc_info=True)

    def _prune_result_records(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        pruned = []
        upload_dir = self._get_upload_dir()
        for record in records:
            filename = secure_filename(str(record.get("filename") or ""))
            if not self._is_allowed_result_filename(filename):
                continue
            file_path = upload_dir / filename
            if file_path.exists() and file_path.is_file():
                pruned.append(record)
        return pruned[-1000:]

    def _register_result(
        self,
        *,
        filename: str,
        owner_username: str,
        source_file: str,
        operation: str,
    ) -> dict[str, Any]:
        record = {
            "id": uuid.uuid4().hex,
            "owner": owner_username,
            "filename": filename,
            "source_file": source_file,
            "operation": operation,
            "created_at": datetime.utcnow().isoformat(),
        }
        with self._result_registry_lock:
            state = self._load_result_registry_unlocked()
            records = self._prune_result_records(state.get("records", []))
            records.append(record)
            state["records"] = records[-1000:]
            self._save_result_registry_unlocked(state)
        return record

    def _resolve_result_record_for_user(self, result_ref: str, owner_username: str) -> dict[str, Any]:
        normalized_ref = str(result_ref or "").strip()
        if not normalized_ref:
            raise HTTPException(status_code=400, detail="结果标识不能为空")

        with self._result_registry_lock:
            state = self._load_result_registry_unlocked()
            records = self._prune_result_records(state.get("records", []))
            state["records"] = records
            self._save_result_registry_unlocked(state)

        # Preferred: result_id lookup
        if self._RESULT_ID_PATTERN.match(normalized_ref):
            any_match = [item for item in records if item["id"] == normalized_ref.lower()]
            if not any_match:
                raise HTTPException(status_code=404, detail="结果不存在或已过期")
            owned = [item for item in any_match if item["owner"] == owner_username]
            if not owned:
                raise HTTPException(status_code=403, detail="无权访问该结果")
            return owned[-1]

        # Backward compatibility: allow filename if and only if owned by user.
        safe_filename = secure_filename(normalized_ref)
        if not self._is_allowed_result_filename(safe_filename):
            raise HTTPException(status_code=400, detail="非法结果标识")

        matched = [item for item in records if item["filename"] == safe_filename]
        if not matched:
            raise HTTPException(status_code=404, detail="结果不存在或已过期")
        owned = [item for item in matched if item["owner"] == owner_username]
        if not owned:
            raise HTTPException(status_code=403, detail="无权访问该结果")
        return owned[-1]

    def _is_allowed_result_filename(self, filename: str) -> bool:
        return bool(filename and self._RESULT_FILE_PATTERN.match(filename))

    def _resolve_result_file(self, filename: str) -> Path:
        safe_filename = secure_filename(filename)
        if not self._is_allowed_result_filename(safe_filename):
            raise HTTPException(status_code=400, detail="Invalid result filename")

        file_path = self._get_upload_dir() / safe_filename
        if not file_path.exists() or not file_path.is_file():
            raise HTTPException(status_code=404, detail=f"文件不存在: {safe_filename}")
        return file_path

    def list_result_files(self) -> list[Path]:
        upload_dir = self._get_upload_dir()
        return [path for path in upload_dir.glob("*_results.xlsx") if self._is_allowed_result_filename(path.name)]

    def get_latest_result_info(self) -> dict:
        result_files = self.list_result_files()
        if not result_files:
            return {"has_result": False}

        latest = max(result_files, key=lambda f: f.stat().st_mtime)
        filename = latest.name
        return {
            "has_result": True,
            "filename": filename,
            "data_url": f"/api/results/{filename}",
            "download_url": f"/api/download/{filename}",
        }

    def get_latest_result_info_for_user(self, owner_username: str) -> dict[str, Any]:
        with self._result_registry_lock:
            state = self._load_result_registry_unlocked()
            records = self._prune_result_records(state.get("records", []))
            state["records"] = records
            self._save_result_registry_unlocked(state)

        user_records = [item for item in records if item.get("owner") == owner_username]
        if not user_records:
            return {"has_result": False}

        latest = max(user_records, key=lambda item: str(item.get("created_at") or ""))
        result_id = str(latest["id"])
        filename = str(latest["filename"])
        return {
            "has_result": True,
            "result_id": result_id,
            "filename": filename,
            "output_file": filename,
            "data_url": f"/api/results/{result_id}",
            "download_url": f"/api/download/{result_id}",
            "created_at": latest.get("created_at", ""),
            "source_file": latest.get("source_file", ""),
            "operation": latest.get("operation", ""),
        }

    def _normalize_sheet_currency(self, sheet_name: str) -> str | None:
        name = str(sheet_name or "").strip().lower().replace(" ", "")
        if name in {"jpy", "日元", "日币"}:
            return "JPY"
        if name in {"rmb", "cny", "人民币"}:
            return "RMB"
        if name in {"usd", "美元", "us$"}:
            return "USD"
        if "其他" in name:
            return "OTHER"
        return None

    def _normalize_currency_value(self, value) -> str:
        text = str(value or "").strip().upper()
        if text in {"CNY", "RMB", "人民币", "RENMINBI"}:
            return "RMB"
        if text in {"JPY", "日元", "日币"}:
            return "JPY"
        if text in {"USD", "美元"}:
            return "USD"
        return text

    def _contains_currency_consumption(self, file_path: str, target_currencies: set[str]) -> bool:
        workbook = pd.ExcelFile(file_path)
        required_cols = {"母公司", "媒介", "服务类型"}
        normalized_targets = {self._normalize_currency_value(item) for item in target_currencies}
        try:
            for sheet in workbook.sheet_names:
                df = pd.read_excel(workbook, sheet_name=sheet)
                if df.empty:
                    continue
                if not required_cols.issubset(set(df.columns.tolist())):
                    continue

                sheet_currency = self._normalize_sheet_currency(sheet)
                if sheet_currency and sheet_currency in normalized_targets:
                    return True
                if sheet_currency in {"USD", "RMB", "JPY"}:
                    continue

                if "币种" not in df.columns:
                    if sheet_currency == "OTHER":
                        raise HTTPException(status_code=400, detail="‘其他币种’Sheet 缺少‘币种’列")
                    continue

                currency_series = df["币种"].apply(self._normalize_currency_value)
                if currency_series.isin(normalized_targets).any():
                    return True

            return False
        finally:
            workbook.close()

    def _contains_rmb_consumption(self, file_path: str) -> bool:
        return self._contains_currency_consumption(file_path, {"RMB"})

    def _contains_jpy_consumption(self, file_path: str) -> bool:
        return self._contains_currency_consumption(file_path, {"JPY"})

    def _build_daily_exchange_context(self, require_snapshot: bool) -> dict:
        today_snapshot = self._daily_fx_snapshot_service.get_today_snapshot()
        if require_snapshot and not today_snapshot:
            raise HTTPException(
                status_code=400,
                detail=(
                    "检测到 RMB 或 JPY 消耗，但今日恒生汇率快照尚未生效。"
                    "请先前往“汇率监控”页面补录今日快照，再重新计算。"
                ),
            )
        return {"hangseng_today": today_snapshot or {}}

    def _record_latest_consumption(self, file_path: str, original_filename: str | None):
        meta_path = self._get_latest_consumption_meta_path()
        payload = {
            "file_path": str(Path(file_path).resolve()),
            "original_filename": original_filename or Path(file_path).name,
        }
        try:
            meta_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        except Exception:
            logger.warning("保存最近消耗文件元数据失败", exc_info=True)

    def _cleanup_failed_upload(self, file_path: Path) -> None:
        if not file_path.exists():
            return

        def _delayed_cleanup(target: Path) -> None:
            if not target.exists():
                return
            try:
                target.unlink(missing_ok=True)
                logger.info("延迟清理上传临时文件成功: %s", target)
            except PermissionError as exc:
                logger.warning("延迟清理上传临时文件失败: %s (%s)", target, exc)

        for attempt in range(3):
            try:
                file_path.unlink(missing_ok=True)
                return
            except PermissionError as exc:
                if attempt < 2:
                    time.sleep(0.1 * (attempt + 1))
                    continue
                logger.warning("上传校验失败后清理文件被占用，保留临时文件: %s (%s)", file_path, exc)
                timer = threading.Timer(5.0, _delayed_cleanup, args=(file_path,))
                timer.daemon = True
                timer.start()

    def _looks_like_consumption_file(self, file_path: Path) -> bool:
        try:
            required_cols = {"母公司", "媒介", "服务类型"}
            workbook = pd.ExcelFile(file_path)
            try:
                for sheet in workbook.sheet_names:
                    header_df = pd.read_excel(workbook, sheet_name=sheet, nrows=0)
                    cols = set(header_df.columns.tolist())
                    if required_cols.issubset(cols):
                        return True
                return False
            finally:
                workbook.close()
        except Exception:
            return False

    def get_latest_consumption_file(self) -> tuple[str, str]:
        """Get latest uploaded consumption file path and original filename."""
        meta_path = self._get_latest_consumption_meta_path()
        if meta_path.exists():
            try:
                payload = json.loads(meta_path.read_text(encoding="utf-8"))
                candidate = Path(str(payload.get("file_path", "")).strip())
                original = str(payload.get("original_filename") or candidate.name)
                if candidate.exists() and candidate.is_file() and self._looks_like_consumption_file(candidate):
                    return str(candidate), original
            except Exception:
                logger.warning("读取最近消耗文件元数据失败，改用目录扫描", exc_info=True)

        upload_dir = self._get_upload_dir()
        candidates = sorted(
            [
                p
                for p in upload_dir.iterdir()
                if p.is_file()
                and p.suffix.lower() in {".xlsx", ".xls"}
                and not p.name.startswith("~$")
                and "_results" not in p.stem.lower()
            ],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

        for candidate in candidates:
            if self._looks_like_consumption_file(candidate):
                return str(candidate), candidate.name

        raise HTTPException(status_code=404, detail="未找到可重算的消耗文件，请先上传消耗数据。")

    def recalculate_latest(self, owner_username: str = "system"):
        """Re-run calculation with latest uploaded consumption file."""
        file_path, original_filename = self.get_latest_consumption_file()
        result = self.process_local_file(
            file_path,
            original_filename,
            owner_username=owner_username,
            operation="recalculate",
        )
        result["source_file"] = Path(file_path).name
        return result

    async def save_uploaded_file(self, file: UploadFile, owner_username: str = "system") -> str:
        """Save uploaded file to disk and return the local path."""
        upload_dir = self._get_upload_dir()
        safe_filename = secure_filename(file.filename)
        self._validate_excel_extension(safe_filename, context="消耗上传文件")
        file_path = upload_dir / safe_filename

        try:
            with open(file_path, "wb") as f:
                shutil.copyfileobj(file.file, f)
            self._validate_consumption_workbook(str(file_path), file.filename or safe_filename)
            self._record_latest_consumption(str(file_path), file.filename)
            self._audit(
                action="upload_consumption",
                actor=owner_username,
                status="success",
                input_file=safe_filename,
            )
            return str(file_path)
        except HTTPException as exc:
            self._cleanup_failed_upload(file_path)
            self._audit(
                action="upload_consumption",
                actor=owner_username,
                status="failed",
                input_file=safe_filename,
                error_message=str(exc.detail),
            )
            raise
        except Exception as exc:
            logger.error("File save failed for %s", safe_filename, exc_info=True)
            self._audit(
                action="upload_consumption",
                actor=owner_username,
                status="failed",
                input_file=safe_filename,
                error_message=str(exc),
            )
            raise HTTPException(status_code=500, detail=f"File save failed: {exc}")

    async def process_calculation(self, file: UploadFile, owner_username: str = "system"):
        file_path = await self.save_uploaded_file(file, owner_username=owner_username)
        return self.process_local_file(
            file_path,
            file.filename or Path(file_path).name,
            owner_username=owner_username,
            operation="calculate",
        )

    def process_local_file(
        self,
        file_path: str,
        original_filename: str,
        *,
        owner_username: str = "system",
        operation: str = "calculate",
    ):
        """Run the core billing calculation and update statistics."""
        try:
            month_hint = self._parse_month_from_filename(original_filename)
            calculation_date = month_hint or None
            has_rmb_rows = self._contains_rmb_consumption(file_path)
            has_jpy_rows = self._contains_jpy_consumption(file_path)
            exchange_context = self._build_daily_exchange_context(require_snapshot=has_rmb_rows or has_jpy_rows)

            output_path = calculate_service_fees(
                file_path,
                contract_path=None,
                use_db=True,
                calculation_date=calculation_date,
                exchange_context=exchange_context,
            )

            self._update_stats_from_result(original_filename, output_path)
            output_name = Path(output_path).name
            result_record = self._register_result(
                filename=output_name,
                owner_username=owner_username,
                source_file=original_filename,
                operation=operation,
            )
            result_id = str(result_record["id"])
            self._audit(
                action=operation,
                actor=owner_username,
                status="success",
                input_file=original_filename,
                output_file=output_name,
                result_ref=result_id,
            )
            return {
                "status": "ok",
                "result_id": result_id,
                "output_file": output_name,
                "download_url": f"/api/download/{result_id}",
                "data_url": f"/api/results/{result_id}",
            }
        except HTTPException as exc:
            self._audit(
                action=operation,
                actor=owner_username,
                status="failed",
                input_file=original_filename,
                error_message=str(exc.detail),
            )
            raise
        except ValueError as exc:
            self._audit(
                action=operation,
                actor=owner_username,
                status="failed",
                input_file=original_filename,
                error_message=str(exc),
            )
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            self._audit(
                action=operation,
                actor=owner_username,
                status="failed",
                input_file=original_filename,
                error_message=str(exc),
            )
            logger.error("Local file processing failed", exc_info=True)
            raise

    def _is_valid_month_string(self, month_text: str) -> bool:
        return bool(month_text and self._MONTH_PATTERN.match(month_text))

    def _normalize_month_value(self, raw_value) -> str | None:
        if pd.isna(raw_value):
            return None

        def _fmt_month(year: int, month: int) -> str | None:
            if 2000 <= year <= 2099 and 1 <= month <= 12:
                return f"{year}-{month:02d}"
            return None

        if isinstance(raw_value, (pd.Timestamp, datetime, date)):
            return _fmt_month(int(raw_value.year), int(raw_value.month))

        numeric_value = None
        if isinstance(raw_value, (int, float)) and not isinstance(raw_value, bool):
            numeric_value = float(raw_value)
        elif isinstance(raw_value, str):
            text = raw_value.strip()
            if not text:
                return None

            compact_match = re.search(r"(20\d{2})\s*[年/\-_]?\s*(\d{1,2})\s*月?", text)
            if compact_match:
                return _fmt_month(int(compact_match.group(1)), int(compact_match.group(2)))

            if re.fullmatch(r"\d+(?:\.\d+)?", text):
                numeric_value = float(text)
            else:
                dt = pd.to_datetime(text, errors="coerce")
                if pd.notna(dt):
                    return _fmt_month(int(dt.year), int(dt.month))
                return None

        if numeric_value is None:
            return None

        rounded = int(round(numeric_value))
        if abs(numeric_value - rounded) < 1e-9:
            if 200001 <= rounded <= 209912:
                return _fmt_month(rounded // 100, rounded % 100)

            if 30000 <= rounded <= 70000:
                excel_dt = pd.to_datetime(rounded, unit="D", origin="1899-12-30", errors="coerce")
                if pd.notna(excel_dt):
                    return _fmt_month(int(excel_dt.year), int(excel_dt.month))

        dt = pd.to_datetime(numeric_value, errors="coerce")
        if pd.notna(dt):
            return _fmt_month(int(dt.year), int(dt.month))
        return None

    def _parse_month_from_filename(self, filename: str) -> str | None:
        patterns = [
            r"(\d{4})[._\-\s]?(\d{1,2})",  # 2024.01 / 2024-01 / 2024 01
            r"(\d{4})年\s*(\d{1,2})月",      # 2024年1月
            r"(20\d{2})(\d{2})",            # 202401
        ]

        for pattern in patterns:
            match = re.search(pattern, filename)
            if not match:
                continue
            try:
                year = int(match.group(1))
                month = int(match.group(2))
            except ValueError:
                continue
            if 2000 <= year <= 2099 and 1 <= month <= 12:
                return f"{year}-{month:02d}"
        return None

    def _update_stats_from_result(self, filename: str, output_path: str):
        """Parse result Excel and update monthly client and billing stats."""
        try:
            month_str = self._parse_month_from_filename(filename)
            res_df = pd.read_excel(output_path)

            res_df["TempConsumption"] = 0.0
            res_df["TempFee"] = 0.0

            if "代投消耗" in res_df.columns:
                res_df["TempConsumption"] += pd.to_numeric(res_df["代投消耗"], errors="coerce").fillna(0)
            if "流水消耗" in res_df.columns:
                res_df["TempConsumption"] += pd.to_numeric(res_df["流水消耗"], errors="coerce").fillna(0)

            if "服务费" in res_df.columns:
                res_df["TempFee"] += pd.to_numeric(res_df["服务费"], errors="coerce").fillna(0)
            if "固定服务费" in res_df.columns:
                res_df["TempFee"] += pd.to_numeric(res_df["固定服务费"], errors="coerce").fillna(0)

            months_to_process: list[tuple[str, pd.DataFrame]] = []
            has_month_col = False

            if "月份归属" in res_df.columns and not res_df["月份归属"].isnull().all():
                has_month_col = True
                try:
                    res_df["_MonthStr"] = res_df["月份归属"].apply(self._normalize_month_value)
                    valid_date_df = res_df.dropna(subset=["_MonthStr"])

                    if not valid_date_df.empty:
                        invalid_count = int((res_df["月份归属"].notna() & res_df["_MonthStr"].isna()).sum())
                        if invalid_count:
                            logger.warning("月份归属列有 %s 行无法识别月份，已忽略", invalid_count)
                        for month_key, group in valid_date_df.groupby("_MonthStr"):
                            if self._is_valid_month_string(month_key):
                                months_to_process.append((month_key, group))
                    else:
                        has_month_col = False
                except Exception as exc:
                    logger.warning("按月份归属分组失败，回退到单月模式: %s", exc)
                    has_month_col = False

            if not has_month_col:
                if not month_str or not self._is_valid_month_string(month_str):
                    raise HTTPException(status_code=400, detail=f"无法从文件名 '{filename}' 或数据列 '月份归属' 识别有效月份。")
                months_to_process.append((month_str, res_df))

            for month_key, current_df in months_to_process:
                self._upsert_monthly_stats_with_retry(month_key, current_df)

        except HTTPException:
            raise
        except Exception as exc:
            logger.error("统计保存失败: %s", exc, exc_info=True)
            raise HTTPException(status_code=500, detail=f"统计保存失败: {exc}")

    def _upsert_monthly_stats_with_retry(self, month: str, df: pd.DataFrame, retries: int = 3):
        last_exc = None
        for attempt in range(1, retries + 1):
            try:
                self._upsert_monthly_stats(month, df)
                return
            except OperationalError as exc:
                last_exc = exc
                msg = str(exc).lower()
                retryable = any(token in msg for token in ("database is locked", "disk i/o error", "busy"))
                if not retryable or attempt >= retries:
                    break
                wait_seconds = 0.4 * attempt
                logger.warning(
                    "月度统计写入失败，准备重试 (%s/%s), month=%s, error=%s",
                    attempt,
                    retries,
                    month,
                    exc,
                )
                time.sleep(wait_seconds)

        if last_exc is not None:
            raise last_exc

    def _upsert_monthly_stats(self, month: str, df: pd.DataFrame):
        if "母公司" in df.columns:
            client_stats = df.groupby("母公司")[["TempConsumption", "TempFee"]].sum().reset_index()
            client_stats = client_stats[(client_stats["TempConsumption"] > 0) | (client_stats["TempFee"] > 0)]

            stats_list = [
                {
                    "name": str(row["母公司"]).strip(),
                    "consumption": row["TempConsumption"],
                    "fee": row["TempFee"],
                }
                for _, row in client_stats.iterrows()
                if pd.notna(row["母公司"]) and str(row["母公司"]).strip()
            ]
            upsert_client_stats_batch(month, stats_list)

        total_consumption = df["TempConsumption"].sum()
        total_fee = df["TempFee"].sum()
        upsert_billing_history(month, total_consumption, total_fee)
        logger.info("Month %s: Total Consumption %s, Total Fee %s", month, total_consumption, total_fee)

    def get_results_data(self, result_ref: str, owner_username: str):
        record = self._resolve_result_record_for_user(result_ref, owner_username)
        file_path = self._resolve_result_file(record["filename"])
        df = pd.read_excel(file_path)

        for col in df.columns:
            if pd.api.types.is_datetime64_any_dtype(df[col]):
                df[col] = df[col].dt.strftime("%Y-%m-%d")
            elif ("月" in str(col) or "日期" in str(col) or "date" in str(col).lower()):
                numeric_vals = pd.to_numeric(df[col], errors="coerce")
                if numeric_vals.notna().any() and (numeric_vals.dropna() > 40000).all() and (numeric_vals.dropna() < 55000).all():

                    def excel_serial_to_date(serial):
                        try:
                            serial_float = float(serial)
                            dt = datetime(1899, 12, 30) + timedelta(days=serial_float)
                            return dt.strftime("%Y-%m")
                        except (ValueError, TypeError):
                            return serial

                    df[col] = df[col].apply(excel_serial_to_date)

        result_df = df.fillna("")
        return {
            "columns": result_df.columns.tolist(),
            "data": result_df.to_dict("records"),
            "total": len(result_df),
        }

    def get_download_path(self, result_ref: str, owner_username: str) -> Path:
        try:
            record = self._resolve_result_record_for_user(result_ref, owner_username)
            file_path = self._resolve_result_file(record["filename"])
            self._audit(
                action="download_result",
                actor=owner_username,
                status="success",
                input_file=record.get("source_file"),
                output_file=record.get("filename"),
                result_ref=str(record.get("id") or result_ref),
            )
            return file_path
        except HTTPException as exc:
            self._audit(
                action="download_result",
                actor=owner_username,
                status="failed",
                result_ref=result_ref,
                error_message=str(exc.detail),
            )
            raise

    async def process_contract_upload(self, file: UploadFile, owner_username: str = "system"):
        upload_dir = self._get_upload_dir()
        safe_filename = secure_filename(file.filename)
        self._validate_excel_extension(safe_filename, context="合同上传文件")
        file_path = upload_dir / safe_filename

        try:
            with open(file_path, "wb") as f:
                shutil.copyfileobj(file.file, f)
            self._validate_contract_workbook(str(file_path))

            from api.migrate import migrate_from_excel

            count = migrate_from_excel(str(file_path))
            self._audit(
                action="upload_contract",
                actor=owner_username,
                status="success",
                input_file=safe_filename,
                metadata={"imported_count": count},
            )
            return {
                "status": "ok",
                "message": f"成功导入 {count} 条客户记录",
            }
        except HTTPException as exc:
            self._audit(
                action="upload_contract",
                actor=owner_username,
                status="failed",
                input_file=safe_filename,
                error_message=str(exc.detail),
            )
            raise
        except ValueError as exc:
            self._audit(
                action="upload_contract",
                actor=owner_username,
                status="failed",
                input_file=safe_filename,
                error_message=str(exc),
            )
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            self._audit(
                action="upload_contract",
                actor=owner_username,
                status="failed",
                input_file=safe_filename,
                error_message=str(exc),
            )
            logger.error("Contract upload failed: %s", exc, exc_info=True)
            raise HTTPException(status_code=500, detail=str(exc))
