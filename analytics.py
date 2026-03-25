"""
Supply Chain Intelligence Platform — NovaMart Operations Analytics
Phase 3: SQL Analytics Layer
Output: novamart_data/analytics/ folder with 8 CSV files
"""

import pandas as pd
import sqlite3
import os

DB_PATH     = "novamart_data/novamart_warehouse.db"
OUTPUT_DIR  = "novamart_data/analytics"
os.makedirs(OUTPUT_DIR, exist_ok=True)

conn = sqlite3.connect(DB_PATH)
print("Connected to warehouse:", DB_PATH)
print("Running analytics queries...\n")

# =============================================================================
# KPI 1: MONTHLY REVENUE TREND
#
# CONCEPT — Window Functions:
# A window function performs a calculation across a set of rows that are
# related to the current row — without collapsing them into a GROUP BY.
#
# LAG(revenue, 1) OVER (ORDER BY year, month) means:
# "For each row, look at the revenue from the PREVIOUS row (1 row back),
#  ordered by time." This gives us last month's revenue sitting right next
#  to this month's revenue — perfect for calculating % change.
#
# INTERVIEW TIP: "I used LAG() window functions to calculate month-over-month
# revenue change directly in SQL without needing Python post-processing."
# =============================================================================
print("[1] Monthly revenue trend...")
kpi1 = pd.read_sql("""
    WITH monthly AS (
        SELECT
            d.year,
            d.month,
            d.month_name,
            ROUND(SUM(fo.revenue), 2)   AS revenue,
            COUNT(fo.order_id)           AS total_orders,
            SUM(fo.quantity)             AS units_sold
        FROM fact_orders fo
        JOIN dim_date d ON fo.date_id = d.date_id
        GROUP BY d.year, d.month, d.month_name
    )
    SELECT
        year,
        month,
        month_name,
        revenue,
        total_orders,
        units_sold,
        -- LAG gets the previous row's value in time order
        LAG(revenue) OVER (ORDER BY year, month) AS prev_month_revenue,
        -- Calculate % change vs last month
        ROUND(
            (revenue - LAG(revenue) OVER (ORDER BY year, month))
            / LAG(revenue) OVER (ORDER BY year, month) * 100
        , 1) AS mom_pct_change
    FROM monthly
    ORDER BY year, month
""", conn)
kpi1.to_csv(f"{OUTPUT_DIR}/kpi1_monthly_revenue.csv", index=False)
print(f"   Saved: {len(kpi1)} rows")
print("   Nov 2024 revenue:", kpi1[kpi1['month']==11].iloc[-1]['revenue'])
print("   Dec 2024 revenue:", kpi1[kpi1['month']==12].iloc[-1]['revenue'])

# =============================================================================
# KPI 2: ON-TIME DELIVERY RATE BY WAREHOUSE
#
# CONCEPT — CASE WHEN for conditional aggregation:
# Instead of filtering rows, we use CASE WHEN inside SUM() to count
# only rows that meet a condition. This lets us get multiple metrics
# in a single query pass — much more efficient than running separate queries.
#
# On-time delivery rate is one of the most watched KPIs in logistics.
# Any warehouse below 85% would trigger a serious management review.
# =============================================================================
print("\n[2] On-time delivery rate by warehouse...")
kpi2 = pd.read_sql("""
    SELECT
        w.warehouse_name,
        w.city,
        w.state,
        COUNT(*)                                        AS total_orders,
        SUM(CASE WHEN fo.status = 'Delivered' THEN 1 ELSE 0 END) AS delivered,
        SUM(CASE WHEN fo.status = 'Delayed'   THEN 1 ELSE 0 END) AS delayed,
        SUM(CASE WHEN fo.status = 'Cancelled' THEN 1 ELSE 0 END) AS cancelled,
        ROUND(
            SUM(CASE WHEN fo.status = 'Delivered' THEN 1.0 ELSE 0 END)
            / COUNT(*) * 100
        , 1) AS on_time_rate_pct
    FROM fact_orders fo
    JOIN dim_warehouses w ON fo.warehouse_id = w.warehouse_id
    GROUP BY w.warehouse_id, w.warehouse_name, w.city, w.state
    ORDER BY on_time_rate_pct DESC
""", conn)
kpi2.to_csv(f"{OUTPUT_DIR}/kpi2_delivery_rate.csv", index=False)
print(f"   Saved: {len(kpi2)} rows")
print(kpi2[['warehouse_name','total_orders','on_time_rate_pct']].to_string(index=False))

# =============================================================================
# KPI 3: SUPPLIER SCORECARD
#
# CONCEPT — Multi-table JOIN + RANK():
# This query joins 3 tables: fact_orders → dim_products → dim_suppliers
# to trace each order back to its supplier.
#
# RANK() OVER (ORDER BY delay_rate DESC) assigns a rank to each supplier
# based on how often they cause delays — rank 1 = worst performer.
# This kind of supplier ranking is used in procurement reviews to decide
# which suppliers to renegotiate contracts with or drop entirely.
# =============================================================================
print("\n[3] Supplier scorecard...")
kpi3 = pd.read_sql("""
    SELECT
        s.supplier_id,
        s.supplier_name,
        s.country,
        s.on_time_rate        AS contracted_on_time_rate,
        s.avg_lead_time_days,
        COUNT(fo.order_id)    AS total_orders,
        SUM(CASE WHEN fo.status = 'Delayed' THEN 1 ELSE 0 END) AS delayed_orders,
        ROUND(
            SUM(CASE WHEN fo.status = 'Delayed' THEN 1.0 ELSE 0 END)
            / COUNT(*) * 100
        , 1) AS actual_delay_rate_pct,
        ROUND(SUM(fo.revenue), 2) AS total_revenue_supplied,
        RANK() OVER (
            ORDER BY
                SUM(CASE WHEN fo.status = 'Delayed' THEN 1.0 ELSE 0 END)
                / COUNT(*) DESC
        ) AS delay_rank
    FROM fact_orders fo
    JOIN dim_products  p ON fo.product_id  = p.product_id
    JOIN dim_suppliers s ON p.supplier_id  = s.supplier_id
    GROUP BY s.supplier_id, s.supplier_name, s.country,
             s.on_time_rate, s.avg_lead_time_days
    ORDER BY delay_rank
""", conn)
kpi3.to_csv(f"{OUTPUT_DIR}/kpi3_supplier_scorecard.csv", index=False)
print(f"   Saved: {len(kpi3)} rows")
print(kpi3[['supplier_name','actual_delay_rate_pct','delay_rank']].to_string(index=False))

# =============================================================================
# KPI 4: INVENTORY TURNOVER RATIO
#
# CONCEPT — Inventory Turnover:
# Inventory Turnover = Units Sold / Average Stock Level
# A HIGH ratio means you're selling through stock quickly (good).
# A LOW ratio means stock is sitting in the warehouse (money tied up, bad).
# Industry benchmark for retail: 4-8x per year.
#
# This is a classic supply chain interview question:
# "How would you identify overstocked products?"
# Answer: "I'd calculate inventory turnover ratio — products with a ratio
# below 2 are candidates for markdowns or reduced reorder quantities."
# =============================================================================
print("\n[4] Inventory turnover by product...")
kpi4 = pd.read_sql("""
    WITH sales AS (
        SELECT
            product_id,
            SUM(quantity) AS total_units_sold
        FROM fact_orders
        WHERE status != 'Cancelled'
        GROUP BY product_id
    ),
    avg_stock AS (
        SELECT
            product_id,
            ROUND(AVG(stock_level), 1) AS avg_stock_level
        FROM fact_inventory
        GROUP BY product_id
    )
    SELECT
        p.product_name,
        p.category,
        s.supplier_name,
        COALESCE(sal.total_units_sold, 0)   AS units_sold,
        COALESCE(ast.avg_stock_level, 0)    AS avg_stock,
        ROUND(
            COALESCE(sal.total_units_sold, 0)
            / NULLIF(ast.avg_stock_level, 0)
        , 2) AS inventory_turnover,
        CASE
            WHEN COALESCE(sal.total_units_sold,0)
                 / NULLIF(ast.avg_stock_level,0) >= 4 THEN 'Healthy'
            WHEN COALESCE(sal.total_units_sold,0)
                 / NULLIF(ast.avg_stock_level,0) >= 2 THEN 'Monitor'
            ELSE 'Overstocked'
        END AS stock_status
    FROM dim_products p
    LEFT JOIN sales       sal ON p.product_id  = sal.product_id
    LEFT JOIN avg_stock   ast ON p.product_id  = ast.product_id
    LEFT JOIN dim_suppliers s ON p.supplier_id = s.supplier_id
    ORDER BY inventory_turnover DESC
""", conn)
kpi4.to_csv(f"{OUTPUT_DIR}/kpi4_inventory_turnover.csv", index=False)
print(f"   Saved: {len(kpi4)} rows")
print(kpi4['stock_status'].value_counts().to_string())

# =============================================================================
# KPI 5: STOCKOUT ANALYSIS
#
# Which products hit zero stock most often and where?
# Stockouts = lost sales = direct revenue impact.
# This feeds the "risk" section of the dashboard.
# =============================================================================
print("\n[5] Stockout analysis...")
kpi5 = pd.read_sql("""
    SELECT
        p.product_name,
        p.category,
        w.warehouse_name,
        w.city,
        COUNT(*)  AS total_stockout_days,
        ROUND(COUNT(*) * 100.0 / 730, 1) AS pct_days_out_of_stock
    FROM fact_inventory fi
    JOIN dim_products   p ON fi.product_id   = p.product_id
    JOIN dim_warehouses w ON fi.warehouse_id = w.warehouse_id
    WHERE fi.stockout_flag = 1
    GROUP BY p.product_id, p.product_name, p.category,
             w.warehouse_id, w.warehouse_name, w.city
    HAVING total_stockout_days > 0
    ORDER BY total_stockout_days DESC
    LIMIT 20
""", conn)
kpi5.to_csv(f"{OUTPUT_DIR}/kpi5_stockouts.csv", index=False)
print(f"   Saved: {len(kpi5)} rows  (top 20 worst stockout situations)")

# =============================================================================
# KPI 6: REVENUE BY CATEGORY AND QUARTER
#
# CONCEPT — Conditional aggregation as a pivot:
# Instead of a separate row per quarter, we use CASE WHEN inside SUM()
# to create one column per quarter. This "wide" format is easier to read
# in dashboards and Excel exports.
# =============================================================================
print("\n[6] Revenue by category and quarter...")
kpi6 = pd.read_sql("""
    SELECT
        p.category,
        ROUND(SUM(CASE WHEN d.quarter=1 THEN fo.revenue ELSE 0 END),2) AS q1_revenue,
        ROUND(SUM(CASE WHEN d.quarter=2 THEN fo.revenue ELSE 0 END),2) AS q2_revenue,
        ROUND(SUM(CASE WHEN d.quarter=3 THEN fo.revenue ELSE 0 END),2) AS q3_revenue,
        ROUND(SUM(CASE WHEN d.quarter=4 THEN fo.revenue ELSE 0 END),2) AS q4_revenue,
        ROUND(SUM(fo.revenue), 2)                                       AS total_revenue
    FROM fact_orders fo
    JOIN dim_products p ON fo.product_id = p.product_id
    JOIN dim_date     d ON fo.date_id    = d.date_id
    GROUP BY p.category
    ORDER BY total_revenue DESC
""", conn)
kpi6.to_csv(f"{OUTPUT_DIR}/kpi6_category_quarterly.csv", index=False)
print(f"   Saved: {len(kpi6)} rows")
print(kpi6.to_string(index=False))

# =============================================================================
# KPI 7: TOP 10 PRODUCTS BY REVENUE
# =============================================================================
print("\n[7] Top 10 products by revenue...")
kpi7 = pd.read_sql("""
    SELECT
        p.product_name,
        p.category,
        s.supplier_name,
        SUM(fo.quantity)          AS units_sold,
        ROUND(SUM(fo.revenue), 2) AS total_revenue,
        ROUND(p.margin_pct, 1)    AS margin_pct,
        RANK() OVER (ORDER BY SUM(fo.revenue) DESC) AS revenue_rank
    FROM fact_orders fo
    JOIN dim_products  p ON fo.product_id = p.product_id
    JOIN dim_suppliers s ON p.supplier_id = s.supplier_id
    WHERE fo.status != 'Cancelled'
    GROUP BY p.product_id, p.product_name, p.category,
             s.supplier_name, p.margin_pct
    ORDER BY revenue_rank
    LIMIT 10
""", conn)
kpi7.to_csv(f"{OUTPUT_DIR}/kpi7_top_products.csv", index=False)
print(f"   Saved: {len(kpi7)} rows")
print(kpi7[['product_name','total_revenue','margin_pct','revenue_rank']].to_string(index=False))

# =============================================================================
# KPI 8: WAREHOUSE PERFORMANCE COMPARISON
# =============================================================================
print("\n[8] Warehouse performance comparison...")
kpi8 = pd.read_sql("""
    SELECT
        w.warehouse_name,
        w.city,
        w.state,
        w.capacity,
        COUNT(fo.order_id)              AS total_orders,
        SUM(fo.quantity)                AS total_units,
        ROUND(SUM(fo.revenue), 2)       AS total_revenue,
        ROUND(AVG(fo.revenue), 2)       AS avg_order_value,
        SUM(CASE WHEN fo.status='Delayed'   THEN 1 ELSE 0 END) AS delayed_orders,
        SUM(CASE WHEN fo.status='Cancelled' THEN 1 ELSE 0 END) AS cancelled_orders,
        ROUND(
            SUM(CASE WHEN fo.status='Delivered' THEN 1.0 ELSE 0 END)
            / COUNT(*) * 100
        , 1) AS fulfillment_rate_pct,
        ROUND(SUM(fo.revenue) / w.capacity, 2) AS revenue_per_capacity_unit
    FROM fact_orders fo
    JOIN dim_warehouses w ON fo.warehouse_id = w.warehouse_id
    GROUP BY w.warehouse_id, w.warehouse_name, w.city, w.state, w.capacity
    ORDER BY total_revenue DESC
""", conn)
kpi8.to_csv(f"{OUTPUT_DIR}/kpi8_warehouse_performance.csv", index=False)
print(f"   Saved: {len(kpi8)} rows")
print(kpi8[['warehouse_name','total_revenue','fulfillment_rate_pct',
            'revenue_per_capacity_unit']].to_string(index=False))

conn.close()

# =============================================================================
# SUMMARY
# =============================================================================
print("\n" + "="*52)
print("  Phase 3 Complete — Analytics Layer Built")
print("="*52)
files = os.listdir(OUTPUT_DIR)
for f in sorted(files):
    size = os.path.getsize(f"{OUTPUT_DIR}/{f}")
    print(f"  {f:<45} {size:>8,} bytes")
print(f"\n  All results saved to: {OUTPUT_DIR}/")
print("="*52)

