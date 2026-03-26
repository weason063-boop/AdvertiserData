from __future__ import annotations

import argparse
import re
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from api.services.calculation_service import CalculationService

VALID_MONTH_RE = re.compile(r"^20\d{2}-(0[1-9]|1[0-2])$")


def _is_valid_month(month: str | None) -> bool:
    return bool(month and VALID_MONTH_RE.match(month))


def _backup_db(db_path: Path) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = db_path.with_name(f"{db_path.stem}.backup.{ts}{db_path.suffix}")
    shutil.copy2(db_path, backup)
    return backup


def _collect_invalid_months(conn: sqlite3.Connection, table: str) -> list[str]:
    rows = conn.execute(f"SELECT DISTINCT month FROM {table}").fetchall()
    invalid = []
    for row in rows:
        month = row[0] if row else None
        if not _is_valid_month(month):
            invalid.append(month)
    return invalid


def _delete_months(conn: sqlite3.Connection, table: str, months: list[str]) -> int:
    if not months:
        return 0
    deleted = 0
    for month in months:
        cur = conn.execute(f"DELETE FROM {table} WHERE month = ?", (month,))
        deleted += cur.rowcount if cur.rowcount is not None else 0
    return deleted


def _find_reimport_file(upload_dir: Path, pattern: str) -> Path:
    candidates = sorted(
        [
            p for p in upload_dir.glob(pattern)
            if p.is_file() and "_results" not in p.stem.lower() and not p.name.startswith("~$")
        ],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise FileNotFoundError(f"未找到待重导文件: {pattern}")
    return candidates[0]


def _print_month_summary(conn: sqlite3.Connection, title: str):
    print(f"\n=== {title} ===")
    rows = conn.execute(
        "SELECT month, total_consumption, total_service_fee FROM billing_history ORDER BY month"
    ).fetchall()
    valid_rows = [r for r in rows if _is_valid_month(r[0])]
    print(f"billing_history 总月份: {len(rows)}，合法月份: {len(valid_rows)}")
    if valid_rows:
        print(f"范围: {valid_rows[0][0]} -> {valid_rows[-1][0]}")
    y2024 = [r for r in valid_rows if isinstance(r[0], str) and r[0].startswith("2024-")]
    print(f"2024 月份数: {len(y2024)}")


def main():
    parser = argparse.ArgumentParser(description="修复看板月份脏数据并重导历史文件")
    parser.add_argument("--db", default="contracts.db", help="SQLite 数据库路径")
    parser.add_argument("--uploads", default="uploads", help="上传目录")
    parser.add_argument("--file", default="2024*.xlsx", help="重导文件匹配模式")
    parser.add_argument("--skip-reimport", action="store_true", help="仅清理脏月份，不重导文件")
    args = parser.parse_args()

    db_path = Path(args.db).resolve()
    upload_dir = Path(args.uploads).resolve()

    if not db_path.exists():
        raise FileNotFoundError(f"数据库不存在: {db_path}")
    if not upload_dir.exists():
        raise FileNotFoundError(f"上传目录不存在: {upload_dir}")

    print(f"数据库: {db_path}")
    print(f"上传目录: {upload_dir}")

    backup = _backup_db(db_path)
    print(f"已备份数据库: {backup}")

    conn = sqlite3.connect(str(db_path))
    try:
        _print_month_summary(conn, "清理前")

        invalid_billing = _collect_invalid_months(conn, "billing_history")
        invalid_client = _collect_invalid_months(conn, "client_monthly_stats")
        invalid_union = sorted({m for m in invalid_billing + invalid_client if m is not None})
        print(f"发现非法月份: {invalid_union if invalid_union else '无'}")

        deleted_billing = _delete_months(conn, "billing_history", invalid_billing)
        deleted_client = _delete_months(conn, "client_monthly_stats", invalid_client)
        conn.commit()
        print(f"已删除 billing_history 行数: {deleted_billing}")
        print(f"已删除 client_monthly_stats 行数: {deleted_client}")

        _print_month_summary(conn, "清理后")
    finally:
        conn.close()

    if args.skip_reimport:
        print("\n已跳过重导步骤。")
        return

    source = _find_reimport_file(upload_dir, args.file)
    print(f"\n开始重导文件: {source.name}")
    service = CalculationService()
    result = service.process_local_file(str(source), source.name)
    print("重导完成:", result)

    conn = sqlite3.connect(str(db_path))
    try:
        _print_month_summary(conn, "重导后")
        rows_2024 = conn.execute(
            "SELECT month, total_consumption, total_service_fee FROM billing_history "
            "WHERE month LIKE '2024-%' ORDER BY month"
        ).fetchall()
        print("2024 账单汇总:")
        for row in rows_2024:
            print(row)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
