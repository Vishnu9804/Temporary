import json
from fastapi import FastAPI, HTTPException, Query
from typing import List, Optional

app = FastAPI(title="Lumina Cosmetics API", description="Simulating a real cosmetic e-commerce client")

# ==========================================
# 1. DATABASE LOADERS
# ==========================================
def get_products_data():
    with open("mockProductDB.json", "r") as f: return json.load(f)
def get_orders_data():
    with open("mockOrderDB.json", "r") as f: return json.load(f)
def get_customers_data():
    with open("mockCustomerDB.json", "r") as f: return json.load(f)
def get_returns_data():
    with open("mockReturnDB.json", "r") as f: return json.load(f)
def get_restocks_data():
    with open("mockRestockDB.json", "r") as f: return json.load(f)

# ==========================================
# 2. APIS
# ==========================================
@app.get("/products")
def get_all_products(category: str = None):
    data = get_products_data()
    products = data.get("products", [])
    if category:
        products = [p for p in products if p["category"].lower() == category.lower()]
    return products

@app.get("/products/search")
def search_products(q: str = Query(...)):
    products = get_products_data().get("products", [])
    search_term = q.lower()
    results = []
    for p in products:
        if (search_term in p.get("name", "").lower() or 
            search_term in p.get("category", "").lower() or 
            any(search_term in ing.lower() for ing in p.get("key_ingredients", []))):
            results.append(p)
    return results

@app.get("/products/{product_id}")
def get_product_detail(product_id: str):
    for p in get_products_data().get("products", []):
        if p["id"] == product_id: return p
    raise HTTPException(status_code=404, detail="Product not found")

@app.get("/orders")
def get_orders(customer_id: str = None):
    orders = get_orders_data().get("orders", [])
    if customer_id:
        orders = [o for o in orders if o["customer_id"] == customer_id]
    return orders

@app.get("/returns")
def get_returns(customer_id: Optional[str] = None):
    returns = get_returns_data().get("returns", [])
    if customer_id:
        returns = [r for r in returns if r["customer_id"] == customer_id]
    return sorted(returns, key=lambda x: x['created_at'], reverse=True)

@app.get("/customers/{customer_id}")
def get_customer_profile(customer_id: str):
    for c in get_customers_data().get("customers", []):
        if c["id"] == customer_id: return c
    raise HTTPException(status_code=404, detail="Customer not found")

@app.get("/restocks")
def get_restocks(product_id: str = None):
    restocks = get_restocks_data().get("restocks", [])
    if product_id:
        restocks = [r for r in restocks if r["product_id"] == product_id]
    return restocks