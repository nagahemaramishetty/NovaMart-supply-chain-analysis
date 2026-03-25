# Supply Chain Intelligence Platform — NovaMart Operations Analytics

A full end-to-end supply chain analytics project simulating a real retail company's data infrastructure — from raw data generation through a star schema data warehouse, SQL analytics, machine learning demand forecasting, and a live Power BI dashboard.

---

## Live Dashboard

[View the Power BI Dashboard →](https://app.powerbi.com/links/sG1gVhLLIL?ctid=88d59d7d-aecb-41b2-90c5-55595de02536&pbi_source=linkShare)

---

## Project Overview

NovaMart is a simulated mid-size US retail company sourcing products from 8 international suppliers, storing inventory across 3 warehouses (Charlotte NC, Atlanta GA, Dallas TX), and fulfilling customer orders nationwide.

This project builds NovaMart's entire analytics infrastructure from scratch — the kind of work a Supply Chain Analyst or Data Analyst would be responsible for at a real company.

**The business problems this project solves:**

- Management cannot see revenue trends or seasonal demand patterns in one place
- No visibility into which suppliers are causing delivery delays
- Inventory is managed reactively — stockouts and overstocking happen because demand is not forecasted
- Warehouse performance is tracked in spreadsheets with no benchmarking

---

## Architecture

```
Raw Data (CSV)
     ↓
Python Data Generation (Faker, pandas, numpy)
     ↓
SQLite Data Warehouse (Star Schema)
     ↓
SQL Analytics Layer (8 KPI queries)
     ↓
ML Demand Forecasting (Random Forest)
     ↓
Power BI Dashboard (3 pages, 12 visuals)
```

---

## Project Structure

```
NovaMart-supply-chain-analysis/
│
├── generate_data.py          # Phase 1: Generate 2 years of realistic supply chain data
├── create_warehouse.py       # Phase 2: Build star schema data warehouse
├── analytics.py              # Phase 3: SQL KPI queries and analytics
├── demand_forecast.py        # Phase 4: ML demand forecasting model
│
├── novamart_data/
│   ├── raw/                  # Generated raw CSVs (5 tables)
│   ├── analytics/            # KPI query outputs (8 CSVs)
│   ├── forecasts/            # ML forecast outputs
│   └── novamart_warehouse.db # SQLite data warehouse
│
└── NovaMart_PowerBI_Data.xlsx # Data source for Power BI dashboard
```

---

## Phase 1 — Data Generation

**File:** `generate_data.py`  
**Tools:** Python, pandas, numpy

Generated 2 years of realistic NovaMart supply chain data across 5 tables:

| Table      | Rows    | Description                                            |
| ---------- | ------- | ------------------------------------------------------ |
| suppliers  | 8       | 8 suppliers across 5 countries with reliability scores |
| products   | 50      | 50 SKUs across 5 categories with cost and pricing      |
| warehouses | 3       | Charlotte DC, Atlanta DC, Dallas DC                    |
| orders     | 44,106  | Every customer order Jan 2023 – Dec 2024               |
| inventory  | 109,500 | Daily stock snapshots per product per warehouse        |

**Key design decision:** Applied a monthly seasonality multiplier to simulate real retail demand patterns — November (1.6x) and December (1.8x) simulate the holiday spike, January (0.7x) simulates the post-holiday slowdown. This is the pattern the ML model learns to predict in Phase 4.

---

## Phase 2 — Data Warehouse & Star Schema

**File:** `create_warehouse.py`  
**Tools:** Python, SQLite, pandas

Built a star schema data warehouse with 2 fact tables and 4 dimension tables:

```
                    dim_suppliers
                         |
dim_date ── fact_orders ── dim_products
                |
           dim_warehouses
                |
          fact_inventory
```

**Tables built:**

- `fact_orders` — central fact table, one row per order, stores measures + foreign keys
- `fact_inventory` — daily stock snapshots with days_of_supply and stockout_flag
- `dim_date` — pre-computed date attributes (year, quarter, month, week, is_weekend)
- `dim_products` — product catalog with margin_pct calculated column
- `dim_suppliers` — supplier master data with reliability metrics
- `dim_warehouses` — warehouse locations and capacity

**Why star schema?** Enables fast analytical queries by separating measurable facts from descriptive context. Every BI tool — Power BI, Tableau, Looker — is built around this pattern.

---

## Phase 3 — SQL Analytics Layer

**File:** `analytics.py`  
**Tools:** Python, SQLite, SQL

Wrote 8 production-grade KPI queries against the warehouse:

| KPI                   | SQL Technique            | Business Question                       |
| --------------------- | ------------------------ | --------------------------------------- |
| Monthly revenue trend | LAG() window function    | How is revenue growing MoM?             |
| On-time delivery rate | CASE WHEN aggregation    | Which warehouses are underperforming?   |
| Supplier scorecard    | RANK() window function   | Which suppliers cause the most delays?  |
| Inventory turnover    | Multi-table JOIN + ratio | Which products are overstocked?         |
| Stockout analysis     | Flag filtering           | Where are we losing sales to stockouts? |
| Category quarterly    | Pivot with CASE WHEN     | Which categories peak in which season?  |
| Top 10 products       | RANK() + JOIN            | What are our best revenue SKUs?         |
| Warehouse comparison  | GROUP BY + KPIs          | How do our 3 DCs compare?               |

**Key findings:**

- All 3 warehouses below 90% on-time delivery benchmark (industry standard)
- DeltaSource Inc. (Vietnam) has the highest delay rate at 10.5% and longest lead time at 25 days
- 44 of 50 products flagged as overstocked — fixed 14-day restock cycle ignores actual demand
- Q4 accounts for ~45% of annual revenue driven by holiday season

---

## Phase 4 — Demand Forecasting with Machine Learning

**File:** `demand_forecast.py`  
**Tools:** Python, scikit-learn, pandas, numpy

Built a Random Forest demand forecasting model to predict daily units sold per product.

### Feature Engineering

Created lag and rolling average features per product:

| Feature     | Description                   |
| ----------- | ----------------------------- |
| lag_7       | Units sold 7 days ago         |
| lag_14      | Units sold 14 days ago        |
| lag_30      | Units sold 30 days ago        |
| rolling_7   | 7-day rolling average demand  |
| rolling_30  | 30-day rolling average demand |
| month       | Captures seasonality          |
| week_number | Sub-monthly patterns          |
| base_demand | Product's inherent popularity |

### Model

- **Algorithm:** Random Forest Regressor (100 trees, max_depth=12)
- **Train set:** Jan 2023 – Sep 2024 (18,966 rows)
- **Test set:** Oct – Dec 2024 holiday season (3,512 rows)
- **Split method:** Time-based — never random shuffle for time series (prevents data leakage)

### Results

| Metric | Value           | Meaning                                            |
| ------ | --------------- | -------------------------------------------------- |
| MAE    | 11.03 units/day | Average prediction error                           |
| RMSE   | 16.02 units/day | Penalises large errors                             |
| MAPE   | 78.6%           | High due to intermittent demand on low-volume days |

### Feature Importance

| Feature      | Importance | Insight                                            |
| ------------ | ---------- | -------------------------------------------------- |
| rolling_7    | 39.7%      | Recent momentum is the strongest demand signal     |
| rolling_30   | 15.2%      | Medium-term trend matters                          |
| month        | 11.7%      | Model correctly learned holiday seasonality        |
| base_demand  | 11.0%      | Product popularity is a stable predictor           |
| category_enc | 0.9%       | Category adds little once product history is known |

**Note on MAPE:** The 78.6% MAPE is inflated by the intermittent demand problem — on days where a specific product sells only 1–2 units at a warehouse, even a small absolute error creates a large percentage error. MAE of 11 units/day is the more meaningful business metric.

### Output

Generated a 90-day forward forecast for Jan–Mar 2025 covering all 50 products (4,500 rows), with a reorder flag for products forecasted above 1.2x their base demand.

---

## Phase 5 — Power BI Dashboard

**Tool:** Power BI Desktop  
**Live link:** [View Dashboard →](https://app.powerbi.com/links/sG1gVhLLIL?ctid=88d59d7d-aecb-41b2-90c5-55595de02536&pbi_source=linkShare)

Built a 3-page interactive dashboard:

### Page 1 — Revenue Overview

- Monthly revenue trend line chart (2023 vs 2024)
- KPI cards: $59.21M total revenue, 44K orders, 84.80% on-time rate
- Revenue by product category horizontal bar chart
- Top 10 products table with margin % and revenue rank

### Page 2 — Supply Chain Operations

- Warehouse revenue comparison (Dallas, Atlanta, Charlotte)
- Fulfillment rate % by warehouse
- Supplier performance scorecard (ranked by delay rate)
- Inventory health status (Overstocked / Monitor breakdown)

### Page 3 — Demand Forecast (ML)

- 90-day demand forecast by category line chart (Jan–Mar 2025)
- Model accuracy KPI cards (MAE, RMSE, MAPE)
- Feature importance bar chart
- Top products by forecasted demand table

---

## Tools & Technologies

| Category          | Tools                                           |
| ----------------- | ----------------------------------------------- |
| Language          | Python 3.12                                     |
| Data manipulation | pandas, numpy                                   |
| Database          | SQLite                                          |
| Machine learning  | scikit-learn (RandomForestRegressor)            |
| Data warehousing  | Star schema, fact/dimension modeling            |
| SQL               | Window functions, CTEs, conditional aggregation |
| Visualization     | Power BI Desktop                                |
| Version control   | Git, GitHub                                     |

---

## How to Run

```bash
# 1. Clone the repo
git clone https://github.com/YOUR_USERNAME/NovaMart-supply-chain-analysis
cd NovaMart-supply-chain-analysis

# 2. Install dependencies
pip install pandas numpy scikit-learn openpyxl

# 3. Generate raw data (~30 seconds)
python generate_data.py

# 4. Build the data warehouse
python create_warehouse.py

# 5. Run SQL analytics
python analytics.py

# 6. Train ML model and generate forecast
python demand_forecast.py
```

Open `NovaMart_PowerBI_Data.xlsx` in Power BI Desktop to explore the dashboard.

---

## Key Interview Talking Points

- Designed a full star schema data warehouse from scratch — 2 fact tables, 4 dimension tables, indexed on all foreign keys
- Used LAG() and RANK() window functions for month-over-month revenue analysis and supplier ranking
- Built a demand forecasting model using Random Forest with engineered lag and rolling features — tested on held-out holiday season data to prevent data leakage
- Identified that 44 of 50 products are overstocked due to fixed restock cycles that ignore actual demand signals
- DeltaSource Inc. identified as highest-risk supplier with 10.5% delay rate and 25-day lead time
- All 3 warehouses below the 90% on-time delivery industry benchmark

---

## Author

**Naga Hema Ramishetty**  
Supply Chain Analytics | Data Analysis | Machine Learning  
[LinkedIn](www.linkedin.com/in/nagaramishetty) · [GitHub](https://github.com/nagahemaramishetty)
