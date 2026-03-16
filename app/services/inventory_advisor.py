import google.generativeai as genai
import requests
import json
from datetime import datetime, timedelta
from app.core.config import settings

genai.configure(api_key=settings.API_KEY)
model = genai.GenerativeModel('gemini-2.5-flash')

async def inventory_engine(client_data: dict):
    # Fetch the exact current date/time the moment this function is called
    current_date = datetime.now()

    # ==========================================
    # STAGE 1: FETCH DATA
    # ==========================================
    try:
        products = requests.get(client_data["products_api"]).json()
        orders = requests.get(client_data["orders_api"]).json()
        restocks = requests.get(client_data["restocks_api"]).json()
    except Exception as e:
        return {"error": f"Failed to fetch data from client APIs: {str(e)}"}

    # ==========================================
    # STAGE 2: MATHEMATICAL PROCESSING
    # ==========================================
    
    # 1. Calculate Average Lead Times per product
    lead_times = {}
    for r in restocks:
        pid = r["product_id"]
        delivery_str = r.get("delivery_date")
        
        # Only calculate historical lead time if the delivery date exists AND is in the past
        if delivery_str is not None:
            delivery_dt = datetime.fromisoformat(delivery_str)
            if delivery_dt <= current_date:
                order_dt = datetime.fromisoformat(r["order_date"])
                days = (delivery_dt - order_dt).days
                
                if pid not in lead_times:
                    lead_times[pid] = []
                lead_times[pid].append(days)

    avg_lead_times = {pid: sum(days)/len(days) for pid, days in lead_times.items()}

    # 2. Calculate Incoming Stock (Handling Nulls and Future Dates)
    incoming_stock = {p["id"]: 0 for p in products}
    for r in restocks:
        pid = r["product_id"]
        delivery_str = r.get("delivery_date")
        
        # Condition 1: Delivery date is null (Client ordered it, but no ETA provided yet)
        if delivery_str is None:
            incoming_stock[pid] += r.get("quantity_ordered", 0)
            
        # Condition 2: Delivery date is explicitly in the future
        else:
            delivery_dt = datetime.fromisoformat(delivery_str)
            if delivery_dt > current_date:
                incoming_stock[pid] += r.get("quantity_ordered", 0)

    # 3. Calculate Sales Velocity (Last 90 Days)
    cutoff_date = current_date - timedelta(days=90)
    sales_90d = {p["id"]: 0 for p in products}
    
    for order in orders:
        order_date = datetime.fromisoformat(order["created_at"])
        if order_date >= cutoff_date and order["status"] != "cancelled":
            for item in order["items"]:
                if item["product_id"] in sales_90d:
                    sales_90d[item["product_id"]] += item["quantity"]

    # 4. Calculate Reorder Metrics
    analysis = []
    for p in products:
        pid = p["id"]
        stock_on_hand = p["stock"]
        on_the_way = incoming_stock.get(pid, 0)
        
        # Math: Daily Sales Velocity (DSV)
        total_sold_90d = sales_90d.get(pid, 0)
        dsv = total_sold_90d / 90.0
        
        # Math: Lead Time (Default to 30 days if they have no historical data)
        lead_time_days = avg_lead_times.get(pid, 30.0)
        
        # Math: Safety Stock (Buffer of 14 days)
        safety_stock = dsv * 14
        
        # Math: Reorder Point
        reorder_point = (dsv * lead_time_days) + safety_stock
        
        # Math: Expected 3-Month Demand
        demand_90d = dsv * 90
        
        # Math: Subtract BOTH stock_on_hand AND on_the_way
        suggested_order = (demand_90d + reorder_point) - (stock_on_hand + on_the_way)
        suggested_order = max(0, int(round(suggested_order))) # Can't order negative
        
        # Days until stockout is based ONLY on what is on the shelf right now
        days_until_stockout = int(stock_on_hand / dsv) if dsv > 0 else 999
        
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
            "current_stock_on_hand": stock_on_hand,
            "incoming_stock_on_the_way": on_the_way,
            "daily_sales_velocity": round(dsv, 2),
            "supplier_lead_time_days": round(lead_time_days, 1),
            "days_until_stock_empty": days_until_stockout,
            "suggested_3_month_order_qty": suggested_order,
            "status": status
        })

    # ==========================================
    # STAGE 3: SORT AND FILTER FOR LLM
    # ==========================================
    analysis.sort(key=lambda x: x["days_until_stock_empty"])
    urgent_items = analysis[:15]

    llm_payload = json.dumps(urgent_items, indent=2)

    # ==========================================
    # STAGE 4: GENERATIVE AI SUMMARY
    # ==========================================
    prompt = f"""
    You are an expert E-commerce Inventory Strategist.
    I have mathematically calculated the 3-month inventory forecast for this client. 
    Below are the top 15 most urgent items that require attention.
    
    Calculated Data:
    {llm_payload}

    Your task is to write a brief, professional Executive Summary for the business owner.
    Do NOT recalculate the numbers. Trust the calculated 'suggested_3_month_order_qty'.
    Pay attention to 'incoming_stock_on_the_way'. If an item has low stock but a shipment is arriving, assure the client they are covered.
    
    Output Format (Strict JSON):
    {{
      "executive_summary": "A 3-sentence overview of the critical stock risks and overarching strategy.",
      "action_items": [
         "Action item 1 referencing specific products and quantities",
         "Action item 2..."
      ]
    }}
    """
    
    llm_output = model.generate_content(prompt).text.strip()
    
    if llm_output.startswith("```json"):
        llm_output = llm_output[7:-3]

    try:
        ai_insights = json.loads(llm_output)
    except:
        ai_insights = {"executive_summary": "Review the data below.", "action_items": []}

    # ==========================================
    # STAGE 5: FINAL PAYLOAD
    # ==========================================
    return {
        "status": "success",
        "strategic_insights": ai_insights,
        "full_data_report": analysis
    }