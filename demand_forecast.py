"""
Supply Chain Intelligence Platform — NovaMart Operations Analytics
Phase 4: Demand Forecasting with Machine Learning
---
Run AFTER create_warehouse.py
Run: python demand_forecast.py
Output: novamart_data/forecasts/
"""

import pandas as pd
import numpy as np
import sqlite3
import os

from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.preprocessing import LabelEncoder

os.makedirs("novamart_data/forecasts", exist_ok=True)
DB_PATH = "novamart_data/novamart_warehouse.db"
conn    = sqlite3.connect(DB_PATH)

print("="*54)
print("  NovaMart Demand Forecasting — Phase 4")
print("="*54)

# =============================================================================
# STEP 1: LOAD DATA FROM WAREHOUSE
# =============================================================================
print("\n[1] Loading data from warehouse...")

daily_demand = pd.read_sql("""
    SELECT
        d.full_date, d.year, d.month, d.quarter,
        d.week_number, d.day_of_week, d.is_weekend,
        fo.product_id, p.category, p.base_demand,
        SUM(fo.quantity) AS units_sold
    FROM fact_orders fo
    JOIN dim_date     d ON fo.date_id    = d.date_id
    JOIN dim_products p ON fo.product_id = p.product_id
    WHERE fo.status != 'Cancelled'
    GROUP BY d.full_date, fo.product_id
    ORDER BY fo.product_id, d.full_date
""", conn)

daily_demand["full_date"] = pd.to_datetime(daily_demand["full_date"])
daily_demand = daily_demand.sort_values(["product_id","full_date"]).reset_index(drop=True)
print(f"   Loaded {len(daily_demand):,} rows | {daily_demand['product_id'].nunique()} products")

# =============================================================================
# STEP 2: FEATURE ENGINEERING
#
# CONCEPT — Lag & Rolling features:
# lag_7  = units sold 7 days ago (1 week of momentum)
# lag_30 = units sold 30 days ago (1 month of momentum)
# rolling_7  = 7-day rolling average (smoothed recent trend)
# rolling_30 = 30-day rolling average (smoothed medium trend)
#
# We use groupby().shift() + transform() per product so lags
# never bleed across product boundaries.
# NOTE: pandas 3.0 drops groupby keys from apply() — use transform() instead.
# =============================================================================
print("\n[2] Engineering features...")

grp = daily_demand.groupby("product_id")["units_sold"]
daily_demand["lag_7"]      = grp.shift(7)
daily_demand["lag_14"]     = grp.shift(14)
daily_demand["lag_30"]     = grp.shift(30)
daily_demand["rolling_7"]  = grp.shift(1).transform(lambda x: x.rolling(7).mean())
daily_demand["rolling_30"] = grp.shift(1).transform(lambda x: x.rolling(30).mean())

# =============================================================================
# STEP 3: ENCODE CATEGORICAL VARIABLES
# ML needs numbers. LabelEncoder: "Apparel"→0, "Electronics"→1, etc.
# =============================================================================
le_product  = LabelEncoder()
le_category = LabelEncoder()
daily_demand["product_enc"]  = le_product.fit_transform(daily_demand["product_id"])
daily_demand["category_enc"] = le_category.fit_transform(daily_demand["category"])

daily_demand = daily_demand.dropna(
    subset=["lag_7","lag_14","lag_30","rolling_7","rolling_30"]
).reset_index(drop=True)
print(f"   Features ready. Rows after cleanup: {len(daily_demand):,}")

# =============================================================================
# STEP 4: TRAIN / TEST SPLIT
# CRITICAL: always split by DATE for time series — never random shuffle.
# Test on Oct–Dec 2024 = holiday season = hardest + most important to get right.
# =============================================================================
print("\n[3] Train/test split by date...")

CUTOFF  = "2024-10-01"
train   = daily_demand[daily_demand["full_date"] <  CUTOFF]
test    = daily_demand[daily_demand["full_date"] >= CUTOFF]

FEATURES = [
    "month", "quarter", "week_number", "day_of_week", "is_weekend",
    "product_enc", "category_enc", "base_demand",
    "lag_7", "lag_14", "lag_30", "rolling_7", "rolling_30"
]
TARGET = "units_sold"

X_train, y_train = train[FEATURES], train[TARGET]
X_test,  y_test  = test[FEATURES],  test[TARGET]

print(f"   Train : {len(X_train):,} rows  ({train['full_date'].min().date()} → {train['full_date'].max().date()})")
print(f"   Test  : {len(X_test):,} rows  ({test['full_date'].min().date()} → {test['full_date'].max().date()})")

# =============================================================================
# STEP 5: TRAIN RANDOM FOREST
# 100 trees (fast) — increase to 200 for better accuracy at cost of time
# =============================================================================
print("\n[4] Training Random Forest (100 trees)...")

model = RandomForestRegressor(
    n_estimators=100, max_depth=12,
    min_samples_leaf=5, random_state=42, n_jobs=-1
)
model.fit(X_train, y_train)
print("   Training complete")

# =============================================================================
# STEP 6: EVALUATE
# MAE  = avg error in units/day — the number to quote in interviews
# RMSE = penalises large errors more heavily
# MAPE = % error — easy for business stakeholders to understand
# =============================================================================
print("\n[5] Model evaluation on held-out test set...")

y_pred = np.maximum(model.predict(X_test), 0)
mae    = mean_absolute_error(y_test, y_pred)
rmse   = np.sqrt(mean_squared_error(y_test, y_pred))
mape   = np.mean(np.abs((y_test - y_pred) / np.maximum(y_test, 1))) * 100

print(f"   MAE  : {mae:.2f} units/day  (avg prediction error)")
print(f"   RMSE : {rmse:.2f} units/day")
print(f"   MAPE : {mape:.1f}%")

# =============================================================================
# STEP 7: FEATURE IMPORTANCE
# =============================================================================
print("\n[6] Feature importance:")

importance_df = pd.DataFrame({
    "feature":    FEATURES,
    "importance": model.feature_importances_
}).sort_values("importance", ascending=False)

for _, row in importance_df.iterrows():
    bar = "█" * int(row["importance"] * 60)
    print(f"   {row['feature']:<15} {row['importance']:.3f}  {bar}")

# =============================================================================
# STEP 8: GENERATE 90-DAY FORECAST (Jan–Mar 2025)
# Batched: build ALL feature rows first, call model.predict() ONCE.
# This is ~50x faster than predicting one row at a time.
# =============================================================================
print("\n[7] Generating 90-day forecast (Jan–Mar 2025)...")

future_dates = pd.date_range(start="2025-01-01", periods=90, freq="D")
products_df  = pd.read_sql("SELECT * FROM dim_products", conn)

all_feat_rows = []
meta          = []

for _, prod in products_df.iterrows():
    pid, cat = prod["product_id"], prod["category"]
    pid_enc  = int(le_product.transform([pid])[0])  if pid in le_product.classes_  else 0
    cat_enc  = int(le_category.transform([cat])[0]) if cat in le_category.classes_ else 0

    hist         = daily_demand[daily_demand["product_id"] == pid].sort_values("full_date")
    recent_sales = hist["units_sold"].tolist()[-30:] if len(hist) >= 30 \
                   else [float(prod["base_demand"])] * 30

    for fdate in future_dates:
        all_feat_rows.append([
            fdate.month, (fdate.month-1)//3+1, int(fdate.strftime("%W")),
            fdate.weekday(), 1 if fdate.weekday()>=5 else 0,
            pid_enc, cat_enc, float(prod["base_demand"]),
            recent_sales[-7]  if len(recent_sales)>=7  else float(prod["base_demand"]),
            recent_sales[-14] if len(recent_sales)>=14 else float(prod["base_demand"]),
            recent_sales[-30] if len(recent_sales)>=30 else float(prod["base_demand"]),
            float(np.mean(recent_sales[-7:])),
            float(np.mean(recent_sales[-30:])),
        ])
        meta.append((fdate.strftime("%Y-%m-%d"), pid, prod["product_name"],
                     cat, float(prod["base_demand"])))

# Single batched predict call
X_fut = pd.DataFrame(all_feat_rows, columns=FEATURES)
preds = np.maximum(model.predict(X_fut), 0)

forecast_rows = []
for i, (fdate, pid, pname, cat, bd) in enumerate(meta):
    forecast_rows.append({
        "forecast_date":   fdate,
        "product_id":      pid,
        "product_name":    pname,
        "category":        cat,
        "predicted_units": round(float(preds[i]), 1),
        "reorder_flag":    1 if preds[i] > bd * 1.2 else 0,
    })

forecast_df = pd.DataFrame(forecast_rows)

# Monthly rollup for Power BI
forecast_df["month"] = pd.to_datetime(forecast_df["forecast_date"]).dt.strftime("%Y-%m")
monthly_summary = (
    forecast_df
    .groupby(["month","product_id","product_name","category"])
    .agg(predicted_units=("predicted_units","sum"), reorder_days=("reorder_flag","sum"))
    .reset_index()
)

# Save all outputs
forecast_df.drop(columns="month").to_csv("novamart_data/forecasts/forecast_90day.csv",           index=False)
monthly_summary.to_csv(                  "novamart_data/forecasts/forecast_monthly_summary.csv",  index=False)
importance_df.to_csv(                    "novamart_data/forecasts/feature_importance.csv",         index=False)
pd.DataFrame([{
    "model":"RandomForestRegressor","mae":round(mae,2),"rmse":round(rmse,2),
    "mape":round(mape,1),"train_rows":len(X_train),"test_rows":len(X_test),
    "n_features":len(FEATURES),"cutoff_date":CUTOFF
}]).to_csv("novamart_data/forecasts/model_metrics.csv", index=False)

conn.close()

print(f"\n   Forecast rows : {len(forecast_df):,}")
print(f"   Products      : {forecast_df['product_id'].nunique()}")
print(f"\n   Top 5 products by predicted Jan 2025 demand:")
top5 = monthly_summary[monthly_summary["month"]=="2025-01"]\
       .sort_values("predicted_units", ascending=False).head()
print(top5[["product_name","category","predicted_units"]].to_string(index=False))

print("\n" + "="*54)
print("  Phase 4 Complete — ML Forecasting Model Built")
print("="*54)
print(f"  MAE  : {mae:.2f} units/day")
print(f"  MAPE : {mape:.1f}%")
print(f"  Saved: novamart_data/forecasts/")
print("="*54)
