"""
Supply Chain Intelligence Platform — NovaMart Operations Analytics
Phase 1: Data Generation
---
Output: novamart_data/raw/ folder with 5 CSV files
"""

import pandas as pd
import numpy as np
import random
from datetime import datetime, timedelta
import os

random.seed(42)
np.random.seed(42)

os.makedirs("novamart_data/raw", exist_ok=True)

# =============================================================================
# TABLE 1: SUPPLIERS
# =============================================================================
suppliers_df = pd.DataFrame([
    ("SUP001","Apex Goods Co.","USA","apex@apexgoods.com",0.95,7),
    ("SUP002","BlueLine Supply","China","contact@bluelinesup.com",0.78,21),
    ("SUP003","CoreTrade Ltd.","India","info@coretrade.in",0.88,14),
    ("SUP004","DeltaSource Inc.","Vietnam","delta@deltasource.com",0.72,25),
    ("SUP005","EverReady Wholesale","USA","sales@everready.com",0.97,5),
    ("SUP006","FastTrack Suppliers","Mexico","ft@fasttrack.mx",0.83,10),
    ("SUP007","GlobalMart Vendors","China","gm@globalmart.cn",0.68,28),
    ("SUP008","HorizonGoods Co.","India","hello@horizongoods.in",0.91,12),
], columns=["supplier_id","supplier_name","country","contact_email","on_time_rate","avg_lead_time_days"])
print("Suppliers:", len(suppliers_df), "rows")

# =============================================================================
# TABLE 2: PRODUCTS
# =============================================================================
product_names = [
    "Wireless Headphones","Smart Watch","Portable Charger","Bluetooth Speaker","USB-C Hub",
    "Running Shoes","Yoga Mat","Gym Gloves","Compression Shorts","Sports Water Bottle",
    "Coffee Maker","Air Fryer","Knife Set","Cutting Board","Meal Prep Containers",
    "Denim Jacket","Casual T-Shirt","Hooded Sweatshirt","Chino Pants","Polo Shirt",
    "Action Figure Set","Board Game","Puzzle 1000pc","Remote Control Car","Building Blocks",
    "Laptop Stand","Desk Organizer","Webcam HD","Mechanical Keyboard","Monitor Light",
    "Resistance Bands","Jump Rope","Foam Roller","Dumbbell Set","Pull-Up Bar",
    "Blender Pro","Electric Kettle","Toaster Oven","Rice Cooker","Food Scale",
    "Winter Jacket","Rain Coat","Beanie Hat","Scarf Set","Leather Gloves",
    "LEGO Classic","Stuffed Animal","Art Supply Kit","Outdoor Kite","Magnetic Tiles",
]
categories = ["Electronics","Apparel","Home & Kitchen","Sports","Toys"]
products = []
for i, name in enumerate(product_names):
    cost = round(random.uniform(5, 180), 2)
    products.append({
        "product_id":   f"PRD{i+1:03d}",
        "product_name": name,
        "category":     categories[i % 5],
        "supplier_id":  f"SUP{random.randint(1,8):03d}",
        "unit_cost":    cost,
        "unit_price":   round(cost * random.uniform(1.4, 2.5), 2),
        "base_demand":  random.randint(3, 45),
    })
products_df = pd.DataFrame(products)
print("Products:", len(products_df), "rows")

# =============================================================================
# TABLE 3: WAREHOUSES
# =============================================================================
warehouses_df = pd.DataFrame([
    {"warehouse_id":"WH001","warehouse_name":"Charlotte DC","city":"Charlotte","state":"NC","capacity":50000},
    {"warehouse_id":"WH002","warehouse_name":"Atlanta DC","city":"Atlanta","state":"GA","capacity":60000},
    {"warehouse_id":"WH003","warehouse_name":"Dallas DC","city":"Dallas","state":"TX","capacity":55000},
])
print("Warehouses:", len(warehouses_df), "rows")

# =============================================================================
# TABLE 4: ORDERS
# Seasonality multiplier simulates real retail demand patterns.
# Nov (1.6x) and Dec (1.8x) = holiday spike our ML model will predict.
# =============================================================================
seasonality = {1:0.70,2:0.75,3:0.90,4:0.95,5:1.00,6:1.00,
               7:1.05,8:1.10,9:1.10,10:1.20,11:1.60,12:1.80}
us_cities = ["Austin","Boston","Chicago","Denver","Houston","Jacksonville",
             "Las Vegas","Los Angeles","Miami","Nashville","New York","Orlando",
             "Philadelphia","Phoenix","Portland","San Diego","San Francisco",
             "Seattle","St. Louis","Tampa"]
us_states = ["AL","AR","AZ","CA","CO","CT","FL","GA","ID","IL","IN","KS",
             "KY","LA","MA","MD","MI","MN","MO","MS","NC","NE","NJ","NM",
             "NV","NY","OH","OK","OR","PA","SC","TN","TX","UT","VA","WA","WI","WV","WY"]

wh_ids  = ["WH001","WH002","WH003"]
pids    = products_df["product_id"].tolist()
prices  = dict(zip(products_df["product_id"], products_df["unit_price"]))
demands = dict(zip(products_df["product_id"], products_df["base_demand"]))

orders = []
order_id   = 1
start_date = datetime(2023, 1, 1)
end_date   = datetime(2024, 12, 31)
cur        = start_date

while cur <= end_date:
    s        = seasonality[cur.month]
    date_str = cur.strftime("%Y-%m-%d")
    for _ in range(int(random.randint(30, 80) * s)):
        pid    = random.choice(pids)
        qty    = max(1, int(np.random.poisson(max(1, demands[pid] * s * 0.3))))
        status = random.choices(
            ["Delivered","Delivered","Delivered","Delayed","Cancelled"],
            weights=[60,15,10,10,5])[0]
        orders.append({
            "order_id":        f"ORD{order_id:06d}",
            "order_date":      date_str,
            "product_id":      pid,
            "warehouse_id":    random.choice(wh_ids),
            "customer_city":   random.choice(us_cities),
            "customer_state":  random.choice(us_states),
            "quantity":        qty,
            "unit_price":      prices[pid],
            "total_amount":    round(qty * prices[pid], 2),
            "shipping_method": random.choice(["Standard","Express","Overnight"]),
            "status":          status,
        })
        order_id += 1
    cur += timedelta(days=1)

orders_df = pd.DataFrame(orders)
print(f"Orders: {len(orders_df):,} rows")

# =============================================================================
# TABLE 5: INVENTORY
# Daily stock snapshot per product per warehouse.
# Pre-grouped orders dictionary = fast lookup (avoids the slow row-by-row scan).
# =============================================================================
print("Building inventory (~30 seconds)...")

orders_grouped = (
    orders_df
    .groupby(["product_id","warehouse_id","order_date"])["quantity"]
    .sum()
    .to_dict()
)

inventory = []
inv_id = 1
for _, product in products_df.iterrows():
    for wid in wh_ids:
        stock = random.randint(300, 1000)
        for d in range(730):
            date_str = (start_date + timedelta(days=d)).strftime("%Y-%m-%d")
            sold     = orders_grouped.get((product["product_id"], wid, date_str), 0)
            restock  = random.randint(100, 400) if d % 14 == 0 else 0
            stock    = max(0, stock - sold + restock)
            inventory.append({
                "inventory_id": f"INV{inv_id:07d}",
                "date":         date_str,
                "product_id":   product["product_id"],
                "warehouse_id": wid,
                "stock_level":  stock,
                "restock_qty":  restock,
            })
            inv_id += 1

inventory_df = pd.DataFrame(inventory)
print(f"Inventory: {len(inventory_df):,} rows")

# =============================================================================
# SAVE
# =============================================================================
suppliers_df.to_csv("novamart_data/raw/suppliers.csv",  index=False)
products_df.to_csv("novamart_data/raw/products.csv",    index=False)
warehouses_df.to_csv("novamart_data/raw/warehouses.csv",index=False)
orders_df.to_csv("novamart_data/raw/orders.csv",        index=False)
inventory_df.to_csv("novamart_data/raw/inventory.csv",  index=False)

print("\n" + "="*48)
print("  NovaMart Data Generation Complete")
print("="*48)
print(f"  Suppliers  : {len(suppliers_df):>8,} rows")
print(f"  Products   : {len(products_df):>8,} rows")
print(f"  Warehouses : {len(warehouses_df):>8,} rows")
print(f"  Orders     : {len(orders_df):>8,} rows")
print(f"  Inventory  : {len(inventory_df):>8,} rows")
print(f"  Revenue    : ${orders_df['total_amount'].sum():>14,.2f}")
print(f"  Saved to   : novamart_data/raw/")
print("="*48)