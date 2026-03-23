import os
import json
import requests
import pandas as pd
from datetime import datetime, timedelta
import google.generativeai as genai
from app.core.config import settings

# Initialize Gemini
genai.configure(api_key=settings.API_KEY)
model = genai.GenerativeModel('gemini-2.5-flash')

# In production, this uses datetime.now(). 
CURRENT_DATE = datetime.now()

def is_date_in_range(target_date: datetime, start_md: str, end_md: str) -> bool:
    """
    Checks if a target date falls within an event range. 
    Crucial for handling events that wrap around the year (e.g., New Year's: 12-26 to 01-15).
    """
    target_md = target_date.strftime("%m-%d")
    if start_md <= end_md:
        return start_md <= target_md <= end_md
    else: 
        # Wraps around the year
        return target_md >= start_md or target_md <= end_md

async def inventory_engine(client_data: dict):
    # ==========================================
    # STAGE 1: FETCH ADAPTER DATA
    # ==========================================
    try:
        products = requests.get(client_data["products_api"]).json()
        orders = requests.get(client_data["orders_api"]).json()
        restocks = requests.get(client_data["restocks_api"]).json()
        
        # We try to fetch the store info (Region & Vertical) from the adapter.
        # If the adapter doesn't have this endpoint yet, we fallback safely to US/Cosmetics.
        store_info = {"region": "US", "vertical": "Cosmetics"}
        if "store_info_api" in client_data:
            try:
                store_info = requests.get(client_data["store_info_api"]).json()
            except:
                pass
    except Exception as e:
        return {"error": f"Failed to fetch data from client APIs: {str(e)}"}

    region = store_info.get("region", "US")

    # ==========================================
    # STAGE 2: LOAD GLOBAL MATRIX
    # ==========================================
    # Securely load the global intelligence matrix from the utils folder
    matrix_path = os.path.join(os.path.dirname(__file__), '..', 'utils', 'global_matrix.json')
    try:
        with open(matrix_path, 'r') as f:
            global_matrix = json.load(f)
    except FileNotFoundError:
        return {"error": "Critical System Error: global_matrix.json not found in app/utils/"}

    # Identify Hemisphere for inverse seasons (US Winter = AUS Summer)
    hemisphere = "Northern_Hemisphere"
    for hemi, data in global_matrix.get("seasonality", {}).items():
        if region in data.get("regions", []):
            hemisphere = hemi
            break

    # ==========================================
    # STAGE 3: BUILD TIME-SERIES DATAFRAME
    # ==========================================
    # We turn chaotic JSON into a pristine daily accounting ledger using Pandas
    sales_records = []
    for order in orders:
        if order.get("status") != "cancelled":
            order_dt = datetime.fromisoformat(order["created_at"]).date()
            for item in order.get("items", []):
                sales_records.append({
                    "date": order_dt,
                    "product_id": item["product_id"],
                    "quantity": item["quantity"]
                })
    
    df = pd.DataFrame(sales_records)
    if not df.empty:
        df['date'] = pd.to_datetime(df['date'])
        daily_sales = df.groupby(['date', 'product_id'])['quantity'].sum().reset_index()
    else:
        daily_sales = pd.DataFrame(columns=['date', 'product_id', 'quantity'])

    # ==========================================
    # STAGE 4: CALCULATE INCOMING & LEAD TIMES
    # ==========================================
    lead_times = {}
    incoming_stock = {p["id"]: 0 for p in products}
    
    for r in restocks:
        pid = r["product_id"]
        delivery_str = r.get("delivery_date")
        order_dt = datetime.fromisoformat(r["order_date"])
        
        # Valid historical delivery to calculate supplier speed
        if delivery_str is not None:
            delivery_dt = datetime.fromisoformat(delivery_str)
            if delivery_dt <= CURRENT_DATE:
                days = (delivery_dt - order_dt).days
                if pid not in lead_times: lead_times[pid] = []
                lead_times[pid].append(days)
        
        # Calculate what is ON THE TRUCK right now
        if delivery_str is None or datetime.fromisoformat(delivery_str) > CURRENT_DATE:
            incoming_stock[pid] += r.get("quantity_ordered", 0)

    # Average lead time (Defaults to 30 days if new supplier)
    avg_lead_times = {pid: sum(lead_times[pid])/len(lead_times[pid]) if pid in lead_times else 30.0 for pid in [p["id"] for p in products]}
    # ==========================================
    # STAGE 5: THE MULTIPLICATIVE ENGINE
    # ==========================================
    analysis = []
    forecast_dates = [CURRENT_DATE + timedelta(days=i) for i in range(90)]
    months_map = {1:"Jan", 2:"Feb", 3:"Mar", 4:"Apr", 5:"May", 6:"Jun", 7:"Jul", 8:"Aug", 9:"Sep", 10:"Oct", 11:"Nov", 12:"Dec"}

    for p in products:
        pid = p["id"]
        stock_on_hand = p.get("stock", 0)
        on_the_way = incoming_stock.get(pid, 0)
        lead_time_days = avg_lead_times.get(pid, 30.0)
        
        # Read the tags generated by the Client Adapter
        core_tags = p.get("core_matrix_tags", ["All_Season_Cosmetics"])
        
        # Calculate Base Daily Sales Velocity (DSV)
        product_history = daily_sales[daily_sales['product_id'] == pid] if not daily_sales.empty else pd.DataFrame()
        if not product_history.empty:
            total_days_active = max(1, (CURRENT_DATE.date() - product_history['date'].min().date()).days)
            base_dsv = product_history['quantity'].sum() / total_days_active
        else:
            base_dsv = 0.0

        # RUN THE 90-DAY FUTURE SIMULATION
        expected_90d_demand = 0.0
        
        for target_date in forecast_dates:
            daily_pred = base_dsv
            month_name = months_map[target_date.month]
            
            # 1. Apply Seasonality
            tag_seasonality = []
            for tag in core_tags:
                val = global_matrix["seasonality"][hemisphere]["monthly_curves"].get(tag, {}).get(month_name)
                if val is not None: tag_seasonality.append(val)
            
            seasonality_mult = sum(tag_seasonality) / len(tag_seasonality) if tag_seasonality else 1.0
            daily_pred *= seasonality_mult
            
            # 2. Apply Event Spikes
            tag_events = []
            for event_name, event_data in global_matrix["events"].items():
                start_md = event_data["dates"]["start"]
                end_md = event_data["dates"]["end"]
                
                if is_date_in_range(target_date, start_md, end_md):
                    region_data = event_data["regional_multipliers"].get(region, {})
                    for tag in core_tags:
                        if tag in region_data:
                            tag_events.append(region_data[tag])
                    break # Stop at the first active event to avoid double-multiplying
            
            event_mult = sum(tag_events) / len(tag_events) if tag_events else 1.0
            daily_pred *= event_mult
            
            # Add to total demand
            expected_90d_demand += daily_pred
            
        # 3. Final Reorder Mathematics
        future_dsv = expected_90d_demand / 90.0 if expected_90d_demand > 0 else base_dsv
        
        safety_stock = future_dsv * 14.0 # 2 weeks buffer
        reorder_point = (future_dsv * lead_time_days) + safety_stock
        
        # The Master Equation: Demand + Minimum Keep - What we already own
        suggested_order = (expected_90d_demand + reorder_point) - (stock_on_hand + on_the_way)
        suggested_order = max(0, int(round(suggested_order)))
        
        days_until_stockout = int(stock_on_hand / future_dsv) if future_dsv > 0 else 999
        
        status = "Healthy"
        if days_until_stockout <= lead_time_days and on_the_way == 0:
            status = "CRITICAL: Reorder Immediately"
        elif days_until_stockout <= lead_time_days and on_the_way > 0:
            status = "WARNING: Low stock, but shipment is arriving"
        elif days_until_stockout <= (lead_time_days + 30):
            status = "WARNING: Order within 30 days"
            
        analysis.append({
            "product_id": pid,
            "product_name": p["name"],
            "core_matrix_tags": core_tags,
            "current_stock_on_hand": stock_on_hand,
            "incoming_stock_on_the_way": on_the_way,
            "predicted_90_day_demand": int(round(expected_90d_demand)),
            "supplier_lead_time_days": round(lead_time_days, 1),
            "days_until_stock_empty": days_until_stockout,
            "suggested_3_month_order_qty": suggested_order,
            "status": status
        })

    # ==========================================
    # STAGE 6: THE EXECUTIVE AI REPORT
    # ==========================================
    # Sort by risk and only pass the top 15 most urgent items to avoid LLM token overload
    analysis.sort(key=lambda x: x["days_until_stock_empty"])
    urgent_items = analysis[:15]
    llm_payload = json.dumps(urgent_items, indent=2)

    prompt = f"""
    You are an elite Supply Chain Analyst acting as a fractional Data Scientist for an e-commerce client.
    Client Profile: Region: {region} | Vertical: {store_info.get('vertical', 'E-commerce')}
    
    I have calculated the 90-day inventory forecast using an advanced Multiplicative Time-Series Model. 
    This model mathematically factors in Base Velocity, {region} Seasonality curves, upcoming Global Events, and Supplier Lead Times based on their product tags.
    
    Below are the top 15 most urgent items:
    {llm_payload}

    Your task is to write a highly professional, strategic Executive Summary for the business owner.
    - Sound like a high-end McKinsey consultant.
    - Highlight the intelligence of the forecast (mention that we factored in seasonal changes, holidays, and incoming stock).
    - Do NOT recalculate the numbers. Trust the 'suggested_3_month_order_qty'.
    - Make the business owner feel incredibly confident that this software protects their revenue.
    
    Output Format (Strict JSON):
    {{
      "executive_summary": "A powerful 3-4 sentence overview of the stock risks, seasonal strategy, and revenue protection.",
      "action_items": [
         "Action item 1 referencing specific products and exact quantities to order.",
         "Action item 2...",
         "Action item 3..."
      ]
    }}
    """
    
    try:
        llm_output = model.generate_content(prompt).text.strip()
        if llm_output.startswith("```json"):
            llm_output = llm_output[7:-3].strip()
        elif llm_output.startswith("```"):
            llm_output = llm_output[3:-3].strip()
        ai_insights = json.loads(llm_output)
    except Exception as e:
        print(f"LLM Parsing Error: {str(e)}")
        ai_insights = {
            "executive_summary": "Forecasting algorithms processed successfully. Review the critical alerts below to prevent lost revenue.",
            "action_items": ["Review products with CRITICAL status immediately."]
        }

    # ==========================================
    # FINAL OUTPUT PAYLOAD
    # ==========================================
    return {
        "status": "success",
        "region_detected": region,
        "hemisphere_applied": hemisphere,
        "strategic_insights": ai_insights,
        "full_data_report": analysis
    }