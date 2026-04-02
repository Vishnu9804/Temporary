import httpx
import asyncio
from datetime import datetime
from typing import Dict, Any, List
import math

def z_score(val: float, mean: float, std: float) -> float:
    """Helper to calculate standard score simulating KMeans standard scaling."""
    if std == 0:
        return 0.0
    return (val - mean) / std

async def whale_hunter_engine(client_data: Dict[str, Any], tenant_id: str) -> Dict[str, Any]:
    # --- Step 0: Fetch Data via Adapters ---
    async with httpx.AsyncClient() as client:
        # Fetch concurrently for speed
        cust_task = client.get(client_data["customers"])
        orders_task = client.get(client_data["orders_api"])
        
        cust_resp, orders_resp = await asyncio.gather(cust_task, orders_task)
        
        if cust_resp.status_code != 200 or orders_resp.status_code != 200:
            raise Exception("Failed to fetch data from client adapters.")
            
        cust_json = cust_resp.json()
        orders_json = orders_resp.json()

    # Safely extract arrays (Adapters might return {"customers": []} or just [])
    customers = cust_json.get("customers", []) if isinstance(cust_json, dict) else cust_json
    orders = orders_json.get("orders", []) if isinstance(orders_json, dict) else orders_json
    
    # Step 1: Data Validation & Multi-Tenancy Check
    if not customers or not orders:
        raise ValueError("Customers or orders arrays retrieved from adapters are empty.")
        
    analysis_date = datetime.now()
            
    # Step 1.5: Parse Dates and Map Data safely
    cust_profiles = {}
    for c in customers:
        c_id = c.get('id') or c.get('customer_id')
        if not c_id: continue
        
        dt_str = c.get('account_created_at')
        # If no creation date, assume very old (datetime.min) so they don't get flagged as newbie
        if dt_str:
            # Handle standard ISO formats gracefully
            dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00")).replace(tzinfo=None)
        else:
            dt = datetime.min
            
        cust_profiles[c_id] = {'account_created_at': dt, 'orders': []}
        
    for o in orders:
        c_id = o.get('customer_id')
        if c_id in cust_profiles:
            dt_str = o.get('created_at')
            if not dt_str: continue
            
            dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00")).replace(tzinfo=None)
            total = float(o.get('total_amount', o.get('subtotal', 0.0)))
            discount = float(o.get('discount_applied', 0.0))
            
            cust_profiles[c_id]['orders'].append({
                'created_at': dt,
                'total_amount': total,
                'discount_applied': discount
            })
            
    # Step 2: Dead Pool Filtering (The 18-Month Rule)
    dead_pool_ignored = 0
    active_customers = {}
    
    for c_id, data in cust_profiles.items():
        c_orders = data['orders']
        if not c_orders:
            dead_pool_ignored += 1
            continue
            
        latest_order_date = max(o['created_at'] for o in c_orders)
        days_since_last_order = (analysis_date - latest_order_date).days
        
        # Flag as Archived/Dead if older than 540 days
        if days_since_last_order > 540:
            dead_pool_ignored += 1
        else:
            active_customers[c_id] = data
            active_customers[c_id]['latest_order_date'] = latest_order_date
            
    if not active_customers:
        return _build_response(tenant_id, "None", len(customers), dead_pool_ignored, 0, 0, [], [], [], [], [])
        
    # Step 3: Data Depth Calculation (Routing the Engine)
    all_active_orders = [o for data in active_customers.values() for o in data['orders']]
    earliest_order_date = min(o['created_at'] for o in all_active_orders)
    latest_active_order_date = max(o['created_at'] for o in all_active_orders)
    
    data_depth_days = (latest_active_order_date - earliest_order_date).days
    engine_used = "Predictive_Clustering" if data_depth_days >= 180 else "Heuristic_Percentile"
    
    # Step 4: RFMD Feature Engineering
    rfmd_data = {}
    for c_id, data in active_customers.items():
        c_orders = data['orders']
        
        recency = (analysis_date - data['latest_order_date']).days
        frequency = len(c_orders)
        monetary = sum(o['total_amount'] for o in c_orders)
        
        sum_total = sum(o['total_amount'] for o in c_orders)
        sum_discount = sum(o['discount_applied'] for o in c_orders)
        discount_affinity = sum_discount / (sum_total + sum_discount) if (sum_total + sum_discount) > 0 else 0.0
        
        account_age = (analysis_date - data['account_created_at']).days
        
        rfmd_data[c_id] = {
            'R': recency, 'F': frequency, 'M': monetary, 'D': discount_affinity, 'Age': account_age
        }
        
    # Segment Arrays
    true_whales, at_risk_whales, deal_chasers, regulars, newbies = [], [], [], [], []

    # Step 5A: The Heuristic Engine (New Clients)
    if engine_used == "Heuristic_Percentile":
        monetary_values = sorted([v['M'] for v in rfmd_data.values()], reverse=True)
        top_15_index = max(0, int(len(monetary_values) * 0.15) - 1)
        top_15_threshold = monetary_values[top_15_index] if monetary_values else 0
        
        for c_id, feats in rfmd_data.items():
            if feats['Age'] < 45 and feats['F'] == 1:
                newbies.append(c_id)
            elif feats['M'] >= top_15_threshold and feats['F'] >= 2 and feats['D'] < 0.20:
                true_whales.append(c_id)
            elif feats['F'] >= 2 and feats['D'] >= 0.30:
                deal_chasers.append(c_id)
            else:
                regulars.append(c_id)
                
    # Step 5B: The Predictive Engine (Mature Clients)
    else:
        def calc_mean_std(vals):
            n = len(vals)
            if n == 0: return 0, 0
            mean = sum(vals) / n
            if n < 2: return mean, 0
            variance = sum((x - mean)**2 for x in vals) / (n - 1)
            return mean, math.sqrt(variance)
            
        r_mean, r_std = calc_mean_std([d['R'] for d in rfmd_data.values()])
        f_mean, f_std = calc_mean_std([d['F'] for d in rfmd_data.values()])
        m_mean, m_std = calc_mean_std([d['M'] for d in rfmd_data.values()])
        d_mean, d_std = calc_mean_std([d['D'] for d in rfmd_data.values()])
        
        for c_id, feats in rfmd_data.items():
            r_z = z_score(feats['R'], r_mean, r_std)
            f_z = z_score(feats['F'], f_mean, f_std)
            m_z = z_score(feats['M'], m_mean, m_std)
            d_z = z_score(feats['D'], d_mean, d_std)
            
            if feats['Age'] < 60 and feats['F'] == 1:
                newbies.append(c_id)
            elif f_z > 0 and m_z > 0 and r_z < 0 and d_z < 0:
                true_whales.append(c_id)
            elif f_z > 0 and m_z > 0 and r_z >= 0 and d_z < 0:
                at_risk_whales.append(c_id)
            elif f_z > 0 and d_z > 0:
                deal_chasers.append(c_id)
            else:
                regulars.append(c_id)

    # Step 6: Formatting and Return
    return _build_response(
        tenant_id, engine_used, len(customers), dead_pool_ignored, len(active_customers),
        data_depth_days, true_whales, at_risk_whales, deal_chasers, regulars, newbies
    )

def _build_response(tenant_id, engine_used, total_rec, dead_ignored, active_proc, depth, tw, arw, dc, reg, nb):
    return {
        "tenant_id": tenant_id,
        "processing_meta": {
            "engine_used": engine_used,
            "total_customers_received": total_rec,
            "dead_pool_ignored": dead_ignored,
            "active_customers_processed": active_proc,
            "data_depth_days": depth
        },
        "segments": {
            "true_whales": tw,
            "at_risk_whales": arw,
            "deal_chasers": dc,
            "regulars": reg,
            "newbies": nb
        }
    }