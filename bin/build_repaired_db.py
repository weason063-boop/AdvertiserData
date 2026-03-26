from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

VALID_MONTH_RE = re.compile(r"^20\d{2}-(0[1-9]|1[0-2])$")


def _is_valid_month(month: str | None) -> bool:
    return bool(month and VALID_MONTH_RE.match(month))


def _normalize_month_value(raw_value) -> str | None:
    if pd.isna(raw_value):
        return None

    def _fmt(y: int, m: int) -> str | None:
        if 2000 <= y <= 2099 and 1 <= m <= 12:
            return f"{y}-{m:02d}"
        return None

    if isinstance(raw_value, pd.Timestamp):
        return _fmt(int(raw_value.year), int(raw_value.month))

    if isinstance(raw_value, str):
        text = raw_value.strip()
        if not text:
            return None
        m = re.search(r"(20\d{2})\s*[年./\-_]?\s*(\d{1,2})\s*月?", text)
        if m:
            return _fmt(int(m.group(1)), int(m.group(2)))
        if re.fullmatch(r"\d+(?:\.\d+)?", text):
            raw_value = float(text)
        else:
            dt = pd.to_datetime(text, errors="coerce")
            if pd.notna(dt):
                return _fmt(int(dt.year), int(dt.month))
            return None

    if isinstance(raw_value, (int, float)) and not isinstance(raw_value, bool):
        num = float(raw_value)
        rounded = int(round(num))
        if abs(num - rounded) < 1e-9:
            if 200001 <= rounded <= 209912:
                return _fmt(rounded // 100, rounded % 100)
            if 30000 <= rounded <= 70000:
                dt = pd.to_datetime(rounded, unit="D", origin="1899-12-30", errors="coerce")
                if pd.notna(dt):
                    return _fmt(int(dt.year), int(dt.month))
        dt = pd.to_datetime(num, errors="coerce")
        if pd.notna(dt):
            return _fmt(int(dt.year), int(dt.month))
    return None


def _find_file(upload_dir: Path, pattern: str) -> Path:
    candidates = sorted(
        [p for p in upload_dir.glob(pattern) if p.is_file() and not p.name.startswith("~$")],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise FileNotFoundError(f"未找到文件: {pattern}")
    return candidates[0]


def _build_repaired_db(src_db: Path, dst_db: Path):
    src_uri = f"file:{src_db.resolve().as_posix()}?mode=ro&immutable=1"
    src_conn = sqlite3.connect(src_uri, uri=True)
    dst_conn = sqlite3.connect(str(dst_db))
    try:
        dst_conn.execute("PRAGMA journal_mode=OFF;")
        dst_conn.execute("PRAGMA synchronous=OFF;")
        src_conn.backup(dst_conn)
        dst_conn.commit()
    finally:
        src_conn.close()
        dst_conn.close()


def _cleanup_invalid_months(conn: sqlite3.Connection):
    invalid = []
    for table in ("billing_history", "client_monthly_stats"):
        rows = conn.execute(f"SELECT DISTINCT month FROM {table}").fetchall()
        bad = [r[0] for r in rows if not _is_valid_month(r[0] if r else None)]
        invalid.extend(bad)
        for month in bad:
            conn.execute(f"DELETE FROM {table} WHERE month = ?", (month,))
    conn.commit()
    return sorted({m for m in invalid if m is not None})


def _upsert_2024_from_results(conn: sqlite3.Connection, result_file: Path):
    df = pd.read_excel(result_file)
    required = {"月份归属", "母公司"}
    if not required.issubset(set(df.columns)):
        raise ValueError(f"结果文件缺少必要列: {required - set(df.columns)}")

    df["TempConsumption"] = 0.0
    df["TempFee"] = 0.0
    if "代投消耗" in df.columns:
        df["TempConsumption"] += pd.to_numeric(df["代投消耗"], errors="coerce").fillna(0)
    if "流水消耗" in df.columns:
        df["TempConsumption"] += pd.to_numeric(df["流水消耗"], errors="coerce").fillna(0)
    if "服务费" in df.columns:
        df["TempFee"] += pd.to_numeric(df["服务费"], errors="coerce").fillna(0)
    if "固定服务费" in df.columns:
        df["TempFee"] += pd.to_numeric(df["固定服务费"], errors="coerce").fillna(0)

    df["_MonthStr"] = df["月份归属"].apply(_normalize_month_value)
    df = df.dropna(subset=["_MonthStr"])
    df = df[df["_MonthStr"].apply(_is_valid_month)]
    if df.empty:
        raise ValueError("没有可导入的有效月份数据。")

    for month, mdf in df.groupby("_MonthStr"):
        client_stats = mdf.groupby("母公司")[["TempConsumption", "TempFee"]].sum().reset_index()
        client_stats = client_stats[
            (client_stats["TempConsumption"] > 0) | (client_stats["TempFee"] > 0)
        ]

        for _, row in client_stats.iterrows():
            name = str(row["母公司"]).strip()
            if not name:
                continue
            conn.execute(
                """
                INSERT INTO client_monthly_stats (month, client_name, consumption, service_fee)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(month, client_name) DO UPDATE SET
                    consumption=excluded.consumption,
                    service_fee=excluded.service_fee
                """,
                (month, name, float(row["TempConsumption"]), float(row["TempFee"])),
            )

        total_consumption = float(mdf["TempConsumption"].sum())
        total_fee = float(mdf["TempFee"].sum())
        conn.execute(
            """
            INSERT INTO billing_history (month, total_consumption, total_service_fee)
            VALUES (?, ?, ?)
            ON CONFLICT(month) DO UPDATE SET
                total_consumption=excluded.total_consumption,
                total_service_fee=excluded.total_service_fee
            """,
            (month, total_consumption, total_fee),
        )
    conn.commit()


def _print_summary(conn: sqlite3.Connection):
    rows = conn.execute(
        "SELECT month, total_consumption, total_service_fee FROM billing_history ORDER BY month"
    ).fetchall()
    valid = [r for r in rows if _is_valid_month(r[0])]
    y2024 = [r for r in valid if r[0].startswith("2024-")]
    print(f"billing_history 月份数: {len(rows)}，合法月份: {len(valid)}")
    if valid:
        print(f"范围: {valid[0][0]} -> {valid[-1][0]}")
    print(f"2024 月份数: {len(y2024)}")
    if y2024:
        print("2024 月份明细:")
        for row in y2024:
            print(row)


def main():
    parser = argparse.ArgumentParser(description="构建修复后的数据库副本（清理非法月份并补 2024 数据）")
    parser.add_argument("--src-db", default="contracts.db")
    parser.add_argument("--uploads", default="uploads")
    parser.add_argument("--result-file", default="2024*_results.xlsx")
    parser.add_argument("--out-db", default="")
    args = parser.parse_args()

    src_db = Path(args.src_db).resolve()
    uploads = Path(args.uploads).resolve()
    if not src_db.exists():
        raise FileNotFoundError(f"源数据库不存在: {src_db}")
    if not uploads.exists():
        raise FileNotFoundError(f"上传目录不存在: {uploads}")

    out_db = Path(args.out_db).resolve() if args.out_db else src_db.with_name(
        f"{src_db.stem}.repaired.{datetime.now().strftime('%Y%m%d_%H%M%S')}{src_db.suffix}"
    )
    result_file = _find_file(uploads, args.result_file)

    print(f"源数据库: {src_db}")
    print(f"结果文件: {result_file}")
    print(f"输出数据库: {out_db}")

    _build_repaired_db(src_db, out_db)

    conn = sqlite3.connect(str(out_db))
    try:
        conn.execute("PRAGMA journal_mode=OFF;")
        conn.execute("PRAGMA synchronous=OFF;")
        invalid = _cleanup_invalid_months(conn)
        print(f"清理非法月份: {invalid if invalid else '无'}")
        _upsert_2024_from_results(conn, result_file)
        _print_summary(conn)
    finally:
        conn.close()

    print("\n已生成修复库。")
    print("下一步：停后端服务后，把 contracts.db 替换为该修复库。")


if __name__ == "__main__":
    main()
