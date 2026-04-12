from sqlalchemy.orm import Session
from app.models.schemas import Order, Product
from collections import defaultdict

async def association_engine(client_id: str, db: Session):
    # 1. FETCH DATA DIRECTLY FROM POSTGRES
    orders = db.query(Order).filter(Order.client_id == client_id).all()
    products_list = db.query(Product).filter(Product.client_id == client_id).all()
    
    # Create dictionary to lookup product prices and names
    products = {p.id: p for p in products_list}
    
    # 2. EXTRACT BASKETS (Transactions)
    baskets = []
    for order in orders:
        if order.status != "cancelled":
            # order.items is a JSONB array from the DB
            items = list(set([item["product_id"] for item in order.items]))
            if len(items) > 1:
                baskets.append(items)
                
    total_baskets = len(baskets)
    if total_baskets == 0:
        return {"status": "success", "message": "No multi-item baskets found in this timeframe.", "bucket_maker_results": []}

    # 3. CALCULATE FREQUENCIES
    item_counts = defaultdict(int)
    pair_counts = defaultdict(int)
    
    for basket in baskets:
        for item in basket:
            item_counts[item] += 1
            
        # Count all pairs in this basket
        for i in range(len(basket)):
            for j in range(i + 1, len(basket)):
                item_a = basket[i]
                item_b = basket[j]
                pair_counts[(item_a, item_b)] += 1
                pair_counts[(item_b, item_a)] += 1
                
    # 4. CALCULATE CONFIDENCE & LIFT (Industry Standards)
    MIN_SUPPORT = 5 # A pair must happen at least 5 times to be considered a real pattern
    
    results = []
    processed_anchors = set()
    
    for (anchor_id, paired_id), count in pair_counts.items():
        if count < MIN_SUPPORT:
            continue
            
        # --- THE MATH (Industry Standard) ---
        # Confidence: How often do they buy B when they buy A?
        confidence = count / item_counts[anchor_id]
        
        # Support of B: How often is B bought across ALL orders?
        support_b = item_counts[paired_id] / total_baskets
        
        # Lift: Does buying A actually INCREASE the chance of buying B?
        lift = confidence / support_b if support_b > 0 else 0
        
        # Ignore noise and non-correlations. 
        # A lift > 1.15 is considered statistically significant in e-commerce.
        if lift < 1.15 or confidence < 0.10:
            continue
            
        # Create the anchor record if it doesn't exist yet
        if anchor_id not in processed_anchors:
            processed_anchors.add(anchor_id)
            results.append({
                "anchor_product": anchor_id,
                "anchor_name": products.get(anchor_id, {}).get("name", "Unknown"),
                "associations": {
                    "core_companions": [],
                    "impulse_addons": []
                }
            })
            
        anchor_obj = next(r for r in results if r["anchor_product"] == anchor_id)
        
        paired_product = products.get(paired_id, {})
        paired_price = paired_product.get("price", 0.0)
        
        association_data = {
            "product_id": paired_id,
            "product_name": paired_product.get("name", "Unknown"),
            "confidence_score": round(confidence, 2),
            "lift_score": round(lift, 2), # Exposing Lift so client sees the math
            "price": paired_price
        }
        
        # ==========================================
        # THE RULE ENGINE (Industry Realities)
        # ==========================================
        # Real-world Core Companion: 30%+ confidence is huge in e-com.
        if confidence >= 0.30:
            association_data["reasoning"] = f"Strong algorithmic lift ({round(lift,2)}x). High probability purchase. Do not heavily discount."
            anchor_obj["associations"]["core_companions"].append(association_data)
            
        # Real-world Impulse Add-on: 10% to 30% confidence, cheap item (<$15)
        elif 0.10 <= confidence < 0.30 and paired_price < 15.0:
            association_data["reasoning"] = f"Actionable add-on (Lift: {round(lift,2)}x). Highly discountable. Use as cart-bumper."
            anchor_obj["associations"]["impulse_addons"].append(association_data)
            
    # 5. CLEANUP & SORTING
    final_results = []
    for r in results:
        if r["associations"]["core_companions"] or r["associations"]["impulse_addons"]:
            # Sort highest Lift to the top as it shows the strongest organic correlation
            r["associations"]["core_companions"].sort(key=lambda x: x["lift_score"], reverse=True)
            r["associations"]["impulse_addons"].sort(key=lambda x: x["lift_score"], reverse=True)
            final_results.append(r)
            
    return {
        "status": "success",
        "rolling_window_baskets_analyzed": total_baskets,
        "bucket_maker_results": final_results
    }