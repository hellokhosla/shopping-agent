"""Test database connectivity and read a few shared PostgreSQL catalog rows."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _positive_limit(value: str) -> int:
    limit = int(value)
    if not 1 <= limit <= 50:
        raise argparse.ArgumentTypeError("limit must be between 1 and 50")
    return limit


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check database connectivity and print a few catalog variants."
    )
    parser.add_argument("--retailer", default="calpak", choices=("calpak", "nordstrom"))
    parser.add_argument("--limit", type=_positive_limit, default=5)
    args = parser.parse_args()

    load_dotenv(REPOSITORY_ROOT / ".env.local")
    load_dotenv(REPOSITORY_ROOT / ".env")
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        parser.error("DATABASE_URL is not set; add it to the repository-root .env or .env.local file.")

    with psycopg.connect(database_url, connect_timeout=10) as connection:
        connection.read_only = True
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT current_database(),
                       (SELECT count(*) FROM retailers),
                       (SELECT count(*) FROM products WHERE is_active),
                       (SELECT count(*) FROM variants)
                """
            )
            summary = cursor.fetchone()
            if summary is None:
                raise RuntimeError("The database did not return a catalog summary.")
            database_name, retailer_count, product_count, variant_count = summary
            print(
                f"Connected to database {database_name!r}: "
                f"{retailer_count} retailers, {product_count} active products, "
                f"{variant_count} variants."
            )

            cursor.execute(
                """
                SELECT p.title, p.brand, v.sku, v.price, v.colour_raw, v.size_norm, v.in_stock
                FROM products AS p
                JOIN variants AS v USING (product_id, retailer_id)
                WHERE p.retailer_id = %s AND p.is_active
                ORDER BY p.title, v.price, v.variant_id
                LIMIT %s
                """,
                (args.retailer, args.limit),
            )
            rows = cursor.fetchall()

    if not rows:
        print(f"No active {args.retailer} catalog variants found.")
        return 0

    print(f"\nSample {args.retailer} variants:")
    for title, brand, sku, price, colour, size, in_stock in rows:
        print(
            f"- {title} | {brand or 'Unknown brand'} | SKU {sku or 'n/a'} | "
            f"${price:.2f} | colour={colour or 'n/a'} | size={size} | "
            f"in_stock={in_stock}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
