from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert
from app.models.schemas import Order, Product, ProductAssociation
from collections import defaultdict
from datetime import datetime

async def association_engine(client_id: str, db: Session):
    # 1. FETCH DATA DIRECTLY FROM POSTGRES
    orders = db.query(Order).filter(Order.client_id == client_id).all()
    products_list = db.query(Product).filter(Product.client_id == client_id).all()
    
    products = {p.id: p for p in products_list}
    
    # 2. EXTRACT BASKETS (Transactions)
    baskets = []
    for order in orders:
        if order.status != "cancelled":
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
            
        for i in range(len(basket)):
            for j in range(i + 1, len(basket)):
                item_a = basket[i]
                item_b = basket[j]
                pair_counts[(item_a, item_b)] += 1
                pair_counts[(item_b, item_a)] += 1
                
    # 4. CALCULATE CONFIDENCE & LIFT
    MIN_SUPPORT = 5 
    results = []
    processed_anchors = set()
    
    for (anchor_id, paired_id), count in pair_counts.items():
        if count < MIN_SUPPORT:
            continue
            
        confidence = count / item_counts[anchor_id]
        support_b = item_counts[paired_id] / total_baskets
        lift = confidence / support_b if support_b > 0 else 0
        
        if lift < 1.15 or confidence < 0.10:
            continue
            
        # Fetch Anchor Price dynamically for relative calculations
        anchor_product = products.get(anchor_id, {})
        anchor_price = float(anchor_product.price) if hasattr(anchor_product, 'price') else 0.0
            
        if anchor_id not in processed_anchors:
            processed_anchors.add(anchor_id)
            results.append({
                "anchor_product": anchor_id,
                "anchor_name": anchor_product.name if hasattr(anchor_product, 'name') else "Unknown",
                "associations": {
                    "core_companions": [],
                    "impulse_addons": []
                }
            })
            
        anchor_obj = next(r for r in results if r["anchor_product"] == anchor_id)
        
        paired_product = products.get(paired_id, {})
        paired_price = float(paired_product.price) if hasattr(paired_product, 'price') else 0.0
        
        association_data = {
            "product_id": paired_id,
            "product_name": paired_product.name if hasattr(paired_product, 'name') else "Unknown",
            "confidence_score": round(confidence, 2),
            "lift_score": round(lift, 2), 
            "price": paired_price
        }
        
        # ==========================================
        # DYNAMIC B2B RULE ENGINE
        # ==========================================
        if confidence >= 0.30:
            association_data["reasoning"] = f"Strong algorithmic lift ({round(lift,2)}x). High probability purchase. Do not heavily discount."
            anchor_obj["associations"]["core_companions"].append(association_data)
            
        elif 0.10 <= confidence < 0.30:
            # Dynamic Logic: An impulse add-on is either objectively cheap OR < 35% of the anchor's price
            if paired_price <= (anchor_price * 0.35) or paired_price < 20.0:
                association_data["reasoning"] = f"Actionable add-on (Lift: {round(lift,2)}x). Highly discountable. Use as cart-bumper."
                anchor_obj["associations"]["impulse_addons"].append(association_data)
            else:
                # If it's expensive but has good lift, don't throw it away! Route it to core_companions.
                association_data["reasoning"] = f"Relevant premium cross-sell (Lift: {round(lift,2)}x). Moderate probability."
                anchor_obj["associations"]["core_companions"].append(association_data)
            
    # 5. CLEANUP & SORTING
    final_results = []
    for r in results:
        if r["associations"]["core_companions"] or r["associations"]["impulse_addons"]:
            r["associations"]["core_companions"].sort(key=lambda x: x["lift_score"], reverse=True)
            r["associations"]["impulse_addons"].sort(key=lambda x: x["lift_score"], reverse=True)
            final_results.append(r)
            
    # ==========================================
    # ---> NEW: DATABASE UPSERT LOGIC <---
    # Stores the generated associations into product_associations
    # ==========================================
    if final_results:
        for r in final_results:
            # PostgreSQL specific 'INSERT ... ON CONFLICT DO UPDATE'
            stmt = insert(ProductAssociation).values(
                client_id=client_id,
                anchor_product_id=r["anchor_product"],
                associations=r["associations"],
                updated_at=datetime.utcnow()
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=['client_id', 'anchor_product_id'], # Primary Key conflict check
                set_={
                    'associations': stmt.excluded.associations,
                    'updated_at': stmt.excluded.updated_at
                }
            )
            db.execute(stmt)
        
        # Save all associations to the database
        db.commit()
            
    return {
        "status": "success",
        "rolling_window_baskets_analyzed": total_baskets,
        "bucket_maker_results": final_results
    }