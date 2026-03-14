"""
Supply Chain Intelligence Platform — NovaMart Operations Analytics
Phase 2: Data Warehouse & Star Schema
---
Output: novamart_data/novamart_warehouse.db
"""

import pandas as pd
import numpy as np
import sqlite3
import os
from datetime import datetime, timedelta

# =============================================================================
# SETUP
# Connect to (or create) the SQLite database file.
# Think of this like creating a new Excel workbook — but it's a real database.
# In production this would be: connect to Snowflake, BigQuery, or PostgreSQL.
# =============================================================================
os.makedirs("novamart_data", exist_ok=True)
DB_PATH = "novamart_data/novamart_warehouse.db"

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Drop tables if they exist so we can re-run cleanly
cursor.executescript("""
    DROP TABLE IF EXISTS fact_orders;
    DROP TABLE IF EXISTS fact_inventory;
    DROP TABLE IF EXISTS dim_products;
    DROP TABLE IF EXISTS dim_suppliers;
    DROP TABLE IF EXISTS dim_warehouses;
    DROP TABLE IF EXISTS dim_date;
""")
conn.commit()
print("Connected to warehouse:", DB_PATH)

# =============================================================================
# DIMENSION 1: dim_date
#
# WHY THIS EXISTS:
# Raw dates like "2023-11-25" are strings — you can't easily ask
# "give me all Q4 orders" or "group by week number" without parsing them.
# dim_date pre-computes every useful date attribute so Power BI and SQL
# can slice data by year, quarter, month, week, or day instantly.
#
# INTERVIEW TIP: "I built a date dimension table that enables time-intelligence
# calculations in Power BI such as month-over-month and year-over-year comparisons."
# =============================================================================
print("\nBuilding dim_date...")

date_rows = []
current = datetime(2023, 1, 1)
end     = datetime(2024, 12, 31)

while current <= end:
    date_rows.append({
        "date_id":      int(current.strftime("%Y%m%d")),  # 20231125 — integer PK, fast to join
        "full_date":    current.strftime("%Y-%m-%d"),
        "year":         current.year,
        "quarter":      (current.month - 1) // 3 + 1,    # 1,2,3,4
        "month":        current.month,
        "month_name":   current.strftime("%B"),           # "November"
        "week_number":  int(current.strftime("%W")),      # 0-52
        "day_of_week":  current.weekday(),                # 0=Monday, 6=Sunday
        "day_name":     current.strftime("%A"),           # "Saturday"
        "is_weekend":   1 if current.weekday() >= 5 else 0,
        "is_month_end": 1 if (current + timedelta(days=1)).month != current.month else 0,
    })
    current += timedelta(days=1)

dim_date = pd.DataFrame(date_rows)
dim_date.to_sql("dim_date", conn, if_exists="replace", index=False)
print(f"  dim_date loaded: {len(dim_date):,} rows")

# =============================================================================
# DIMENSION 2: dim_suppliers
#
# Cleaned directly from raw CSV. on_time_rate will be used in Phase 4 SQL
# analytics to rank suppliers and flag poor performers.
# =============================================================================
print("\nLoading dimension tables...")

dim_suppliers = pd.read_csv("novamart_data/raw/suppliers.csv")
dim_suppliers.to_sql("dim_suppliers", conn, if_exists="replace", index=False)
print(f"  dim_suppliers loaded: {len(dim_suppliers):,} rows")

# =============================================================================
# DIMENSION 3: dim_products
#
# We add a calculated column: margin_pct = profit margin percentage.
# Adding derived columns in the warehouse means every downstream report
# automatically gets it without recalculating each time.
# =============================================================================
dim_products = pd.read_csv("novamart_data/raw/products.csv")
dim_products["margin_pct"] = round(
    (dim_products["unit_price"] - dim_products["unit_cost"]) / dim_products["unit_price"] * 100, 2
)
dim_products.to_sql("dim_products", conn, if_exists="replace", index=False)
print(f"  dim_products loaded: {len(dim_products):,} rows  (+ margin_pct column added)")

# =============================================================================
# DIMENSION 4: dim_warehouses
# =============================================================================
dim_warehouses = pd.read_csv("novamart_data/raw/warehouses.csv")
dim_warehouses.to_sql("dim_warehouses", conn, if_exists="replace", index=False)
print(f"  dim_warehouses loaded: {len(dim_warehouses):,} rows")

# =============================================================================
# FACT TABLE 1: fact_orders
#
# This is the most important table — the center of our star schema.
# Key transformation: we convert order_date string → date_id integer
# so it can join to dim_date efficiently.
#
# We also add revenue_after_status: cancelled orders contribute $0 revenue.
# This is a business rule we encode once in the warehouse so every report
# automatically handles it correctly.
# =============================================================================
print("\nBuilding fact_orders...")

raw_orders = pd.read_csv("novamart_data/raw/orders.csv")

# Convert date string to integer date_id (e.g. "2023-11-25" → 20231125)
raw_orders["date_id"] = pd.to_datetime(raw_orders["order_date"]).dt.strftime("%Y%m%d").astype(int)

# Business rule: cancelled orders = $0 revenue
raw_orders["revenue"] = raw_orders.apply(
    lambda r: 0 if r["status"] == "Cancelled" else r["total_amount"], axis=1
)

# Select only the columns the fact table needs
fact_orders = raw_orders[[
    "order_id",
    "date_id",          # FK → dim_date
    "product_id",       # FK → dim_products
    "warehouse_id",     # FK → dim_warehouses
    "quantity",
    "unit_price",
    "total_amount",
    "revenue",          # 0 if cancelled
    "shipping_method",
    "status",
    "customer_city",
    "customer_state",
]]

fact_orders.to_sql("fact_orders", conn, if_exists="replace", index=False)
print(f"  fact_orders loaded: {len(fact_orders):,} rows")

# =============================================================================
# FACT TABLE 2: fact_inventory
#
# A second fact table for daily stock levels. This shares dim_products,
# dim_warehouses, and dim_date with fact_orders — that shared dimension
# structure is called a "fact constellation schema" or "galaxy schema".
#
# Adds: days_of_supply = how many days of stock remain at current demand.
# Adds: stockout_flag = 1 when stock hits 0 (a critical supply chain KPI).
# =============================================================================
print("\nBuilding fact_inventory...")

raw_inv = pd.read_csv("novamart_data/raw/inventory.csv")

# Add date_id foreign key
raw_inv["date_id"] = pd.to_datetime(raw_inv["date"])\
    .dt.strftime("%Y%m%d").astype(int)

# Calculate daily demand per product (average units sold per day across all warehouses)
daily_demand = (
    raw_orders.groupby("product_id")["quantity"].sum() / 730
).rename("avg_daily_demand").reset_index()

raw_inv = raw_inv.merge(daily_demand, on="product_id", how="left")
raw_inv["avg_daily_demand"] = raw_inv["avg_daily_demand"].fillna(1)

# Days of supply: how many days until stockout at current demand rate
raw_inv["days_of_supply"] = (
    raw_inv["stock_level"] / raw_inv["avg_daily_demand"]
).round(1).clip(upper=999)

# Stockout flag: 1 = stock is at zero (serious supply chain problem)
raw_inv["stockout_flag"] = (raw_inv["stock_level"] == 0).astype(int)

fact_inventory = raw_inv[[
    "inventory_id",
    "date_id",          # FK → dim_date
    "product_id",       # FK → dim_products
    "warehouse_id",     # FK → dim_warehouses
    "stock_level",
    "restock_qty",
    "days_of_supply",
    "stockout_flag",
]]

fact_inventory.to_sql("fact_inventory", conn, if_exists="replace", index=False)
print(f"  fact_inventory loaded: {len(fact_inventory):,} rows")

# =============================================================================
# CREATE INDEXES
#
# An index is like a book's index — it lets the database find rows fast
# without scanning the entire table. We index all foreign key columns
# because those are what we join and filter on in every query.
# =============================================================================
print("\nCreating indexes...")

cursor.executescript("""
    CREATE INDEX IF NOT EXISTS idx_fact_orders_date      ON fact_orders(date_id);
    CREATE INDEX IF NOT EXISTS idx_fact_orders_product   ON fact_orders(product_id);
    CREATE INDEX IF NOT EXISTS idx_fact_orders_warehouse ON fact_orders(warehouse_id);
    CREATE INDEX IF NOT EXISTS idx_fact_orders_status    ON fact_orders(status);
    CREATE INDEX IF NOT EXISTS idx_fact_inv_date         ON fact_inventory(date_id);
    CREATE INDEX IF NOT EXISTS idx_fact_inv_product      ON fact_inventory(product_id);
    CREATE INDEX IF NOT EXISTS idx_fact_inv_warehouse    ON fact_inventory(warehouse_id);
    CREATE INDEX IF NOT EXISTS idx_fact_inv_stockout     ON fact_inventory(stockout_flag);
""")
conn.commit()
print("  Indexes created on all foreign key columns")

# =============================================================================
# VALIDATION — 3 test queries
#
# Always validate after loading. These 3 queries confirm:
# 1. Row counts match what we generated
# 2. Joins between fact and dimension tables work correctly
# 3. Business logic (revenue=0 for cancelled) is applied
# =============================================================================
print("\n" + "="*52)
print("  VALIDATION QUERIES")
print("="*52)

# Test 1: Row counts in every table
print("\n[1] Row counts:")
tables = ["dim_date","dim_suppliers","dim_products","dim_warehouses",
          "fact_orders","fact_inventory"]
for t in tables:
    count = pd.read_sql(f"SELECT COUNT(*) as n FROM {t}", conn).iloc[0,0]
    print(f"    {t:<22}: {count:>9,} rows")

# Test 2: Revenue by year — proves fact + dim_date join works
print("\n[2] Revenue by year (fact_orders JOIN dim_date):")
q2 = pd.read_sql("""
    SELECT
        d.year,
        COUNT(*)               AS total_orders,
        SUM(fo.quantity)       AS total_units,
        ROUND(SUM(fo.revenue),2) AS total_revenue
    FROM fact_orders fo
    JOIN dim_date d ON fo.date_id = d.date_id
    GROUP BY d.year
    ORDER BY d.year
""", conn)
print(q2.to_string(index=False))

# Test 3: Top 3 categories by revenue — proves product dimension join works
print("\n[3] Revenue by product category (JOIN dim_products):")
q3 = pd.read_sql("""
    SELECT
        p.category,
        ROUND(SUM(fo.revenue), 2) AS revenue,
        SUM(fo.quantity)          AS units_sold
    FROM fact_orders fo
    JOIN dim_products p ON fo.product_id = p.product_id
    GROUP BY p.category
    ORDER BY revenue DESC
""", conn)
print(q3.to_string(index=False))

conn.close()

print("\n" + "="*52)
print("  Phase 2 Complete — Warehouse built successfully")
print(f"  Database: {DB_PATH}")
print("="*52)