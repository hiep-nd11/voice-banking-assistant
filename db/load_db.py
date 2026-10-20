"""
Nạp schema + dữ liệu mock vào Postgres (không cần cài psql).

    export DATABASE_URL=postgresql://user:pass@host:5432/dbname
    python db/load_db.py            # tạo lại schema vb + nạp seed.sql
    python db/load_db.py --check    # chỉ kiểm tra kết nối và đếm bản ghi

CẢNH BÁO: lệnh mặc định DROP SCHEMA vb CASCADE (xóa toàn bộ dữ liệu cũ trong schema vb).
"""
import argparse
import os
import sys
from pathlib import Path

import psycopg

HERE = Path(__file__).resolve().parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--seed", default=str(HERE / "seed.sql"))
    a = ap.parse_args()
    url = os.getenv("DATABASE_URL")
    if not url:
        sys.exit("Chưa đặt DATABASE_URL")
    with psycopg.connect(url, autocommit=True) as c:
        if not a.check:
            print("-> schema.sql")
            c.execute((HERE / "schema.sql").read_text(encoding="utf-8"))
            print("->", a.seed)
            c.execute(Path(a.seed).read_text(encoding="utf-8"))
        for t in ["customers", "accounts", "categories", "transactions", "beneficiaries", "products",
                  "pending_actions", "tool_audit_log"]:
            n = c.execute(f"SELECT count(*) FROM vb.{t}").fetchone()[0]
            print(f"   vb.{t:<16} {n:>6}")
    print("OK")


if __name__ == "__main__":
    main()
