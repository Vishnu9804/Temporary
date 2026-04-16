import httpx
from typing import Dict, Any
from sqlalchemy.orm import Session
from app.models.schemas import Product, Order
from datetime import datetime, timedelta

async def price_advisor_engine(client_id: str, db: Session):
    # Fetch Data Direct from DB
    products_db = db.query(Product).filter(Product.client_id == client_id).all()
    
    if not products_db:
        raise ValueError("No products found for this tenant.")

    # ==========================================
    # OPTION B: BULK FETCH SALES VELOCITY
    # ==========================================
    # We fetch all orders from the last 30 days in ONE query to save DB read costs
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    recent_orders = db.query(Order).filter(
        Order.client_id == client_id,
        Order.created_at >= thirty_days_ago,
        Order.status != "cancelled"
    ).all()

    # Build an in-memory dictionary: { "PROD-123": 45, "PROD-456": 12 }
    sales_30d_map = {}
    for order in recent_orders:
        for item in order.items:
            pid = item.get("product_id")
            qty = item.get("quantity", 0)
            if pid:
                sales_30d_map[pid] = sales_30d_map.get(pid, 0) + qty
    # ==========================================

    advised_changes = []

    for p in products_db:
        p_id = p.id
        p_name = p.name
        current_price = float(p.price)
        cost_price = float(p.cost_price)
        min_price = float(p.min_allowable_price or 0.0)
        stock = p.stock
        tags = p.core_matrix_tags or []
        competitors = p.competitor_pricing_data or []

        # 1. Buffer & Classification
        is_premium = "Premium_Cosmetics" in tags
        buffer_percentage = 10.0 if is_premium else 5.0
        
        # 2. Advanced Supply Chain Metrics (Days of Inventory)
        # Pull the sales volume from our in-memory map instead of the product object
        sales_30d = float(sales_30d_map.get(p_id, 0.0))
            
        is_scarcity = False
        is_overstock = False
        stock_context_str = f"{stock} items"
        
        if sales_30d > 0:
            daily_velocity = sales_30d / 30.0
            days_of_inventory = stock / daily_velocity
            
            # SCARCITY = Less than 2 weeks of supply remaining
            is_scarcity = days_of_inventory < 14.0
            # OVERSTOCK = Trapped capital. More than 3 months of supply.
            is_overstock = days_of_inventory > 90.0
            
            if is_scarcity:
                stock_context_str = f"very low stock (only {int(days_of_inventory)} days of supply left)"
            elif is_overstock:
                stock_context_str = f"too much stock (over {int(days_of_inventory)} days of supply sitting in the warehouse)"
            else:
                stock_context_str = f"a healthy amount of stock ({int(days_of_inventory)} days of supply)"
                
        elif sales_30d == 0: # It literally never sells
            is_scarcity = False
            is_overstock = stock > 20 # Even a small amount is dead-stock if sales are 0
            stock_context_str = f"{stock} items (and nobody has bought one recently)"
        else:
            # Fallback if something goes wrong
            is_scarcity = stock < 50
            is_overstock = stock > 500
            stock_context_str = f"a huge pile of {stock} items" if is_overstock else (f"only {stock} items" if is_scarcity else f"{stock} items")

        
        # Group Competitors
        in_stock_comps = [c for c in competitors if c.get("is_in_stock", False)]
        out_of_stock_comps = [c for c in competitors if not c.get("is_in_stock", False)]

        target_price = current_price
        reason_code = "OPTIMAL"
        advice = "Price is perfect, no changes needed right now."
        
        # Context variables
        lowest_comp = None
        lowest_price = current_price
        names_str = ""

        # --- 3. Inventory-Aware & Margin-Aware Mathematics ---
        if in_stock_comps:
            # Find the absolute cheapest in-stock competitor
            lowest_comp = min(in_stock_comps, key=lambda x: float(x.get("observed_price", float('inf'))))
            lowest_price = float(lowest_comp.get("observed_price", current_price))
            comp_name = lowest_comp.get('competitor_name', 'Unknown')
            
            if lowest_price < current_price:
                # Competitor is Cheaper -> Use Midway Math instead of blindly matching
                if is_scarcity:
                    # Don't chase the bottom. Protect margin because we are about to run out anyway.
                    target_price = current_price
                    reason_code = "SCARCITY_HOLD"
                elif is_overstock:
                    # Aggressively compete to clear warehouse, but stay slightly above their exact bottom
                    price_diff = current_price - lowest_price
                    target_price = lowest_price + (price_diff * 0.15)
                    reason_code = "OVERSTOCK_AGGRESSIVE_COMPETE"
                else:
                    # NORMAL: The Exact "Midway" Solution to stay competitive but protect margin
                    target_price = (current_price + lowest_price) / 2.0
                    reason_code = "STRATEGIC_MIDWAY_ADJUSTMENT"
            
            elif lowest_price > current_price:
                # We are the Cheapest -> Should we raise the price?
                if is_overstock:
                    # If we have too much stock, DON'T raise the price. Being the cheapest is good here.
                    target_price = current_price
                    reason_code = "OVERSTOCK_MAINTAIN_CHEAPEST"
                else:
                    # Maximize Profit Margin safely by sitting exactly 2% cheaper than them
                    potential_price = lowest_price * 0.98
                    if potential_price > current_price:
                        target_price = potential_price
                        reason_code = "PROFIT_MAXIMIZATION_UNDER_COMPETITOR"
        else:
            # No competitors are in stock
            if out_of_stock_comps:
                oos_names = [c.get('competitor_name', 'Unknown') for c in out_of_stock_comps]
                names_str = ", ".join(oos_names[:3])
                if len(oos_names) > 3:
                    names_str += " and others"

                if is_scarcity:
                    # Premium Scarcity Pricing
                    target_price = current_price * (1 + (buffer_percentage / 100))
                    reason_code = "COMPETITOR_OOS_SCARCITY_PREMIUM"
                elif is_overstock:
                    # VOLUME PLAY: Don't raise price, capture the volume to clear warehouse
                    target_price = current_price
                    reason_code = "COMPETITOR_OOS_HOLD_TO_CLEAR"
                else:
                    # NORMAL: Safely raise price by buffer since we have a monopoly right now
                    target_price = current_price * (1 + (buffer_percentage / 100))
                    reason_code = "COMPETITOR_OUT_OF_STOCK"
            else:
                # No competitors exist in the data
                if is_overstock:
                    # Proactive discounting on dead inventory
                    target_price = current_price * (1 - (buffer_percentage / 100))
                    reason_code = "OVERSTOCK_PROACTIVE_DISCOUNT"

        # --- 4. Strict Margin Protection Floor ---
        advised_price = max(target_price, min_price)
        advised_price = round(advised_price, 2)

        if advised_price == min_price and target_price < min_price and reason_code in ["STRATEGIC_MIDWAY_ADJUSTMENT", "OVERSTOCK_AGGRESSIVE_COMPETE"]:
            reason_code = "MIN_PRICE_FLOOR_REACHED"

        # --- Generate 10-Year-Old Friendly Explanations ---
        if reason_code == "SCARCITY_HOLD":
            advice = f"Keep the price at ${current_price:.2f}. Competitor '{comp_name}' dropped their price to ${lowest_price:.2f}, but we have {stock_context_str}! Let's save them for buyers willing to pay our price instead of fighting them."
        elif reason_code == "STRATEGIC_MIDWAY_ADJUSTMENT":
            advice = f"Lower the price from ${current_price:.2f} to ${advised_price:.2f}. Competitor '{comp_name}' is selling it low at ${lowest_price:.2f}. Instead of copying their exact price and hurting our margin, we found a smart midway point to stay competitive."
        elif reason_code == "OVERSTOCK_AGGRESSIVE_COMPETE":
            advice = f"Lower the price to ${advised_price:.2f}. We have {stock_context_str}! Competitor '{comp_name}' is at ${lowest_price:.2f}. We reduced our price to compete and clear our warehouse faster."
        elif reason_code == "OVERSTOCK_MAINTAIN_CHEAPEST":
            advice = f"Keep the price at ${current_price:.2f}. We are currently the cheapest (competitor '{comp_name}' is at ${lowest_price:.2f}). Since we have {stock_context_str}, keeping our price low will help us sell them out faster."
        elif reason_code == "PROFIT_MAXIMIZATION_UNDER_COMPETITOR":
            advice = f"Raise the price to ${advised_price:.2f}. We are currently the cheapest! The next competitor '{comp_name}' is selling it for ${lowest_price:.2f}. We can safely raise our price and make more profit, while still being the cheaper option."
        elif reason_code == "MIN_PRICE_FLOOR_REACHED":
            advice = f"Lower the price to ${advised_price:.2f}. Competitor '{comp_name}' is selling it very cheap at ${lowest_price:.2f}, but we cannot go below our absolute minimum cost of ${min_price:.2f}. This is the lowest we can safely go."
        elif reason_code == "COMPETITOR_OOS_SCARCITY_PREMIUM":
            advice = f"Raise the price to ${advised_price:.2f}! Competitors ({names_str}) are totally sold out. Since we have {stock_context_str}, people will gladly pay a bit extra to get it from us."
        elif reason_code == "COMPETITOR_OOS_HOLD_TO_CLEAR":
            advice = f"Keep the price at ${current_price:.2f}. Competitors ({names_str}) are sold out, but we have {stock_context_str}. Keep the price exactly the same to grab all their customers and empty our shelves quickly."
        elif reason_code == "COMPETITOR_OUT_OF_STOCK":
            advice = f"Raise the price to ${advised_price:.2f}! Competitors ({names_str}) ran out of this item. We can safely ask for more money because they have to buy from us right now."
        elif reason_code == "OVERSTOCK_PROACTIVE_DISCOUNT":
            advice = f"Put it on sale for ${advised_price:.2f}! We have {stock_context_str} just sitting there collecting dust. Let's make it slightly cheaper to convince people to buy it."

        # --- 5. Delta Threshold Check (Only output if changes are meaningful > 1%) ---
        if current_price > 0:
            diff_percentage = (abs(current_price - advised_price) / current_price) * 100
        else:
            diff_percentage = 0.0

        if diff_percentage >= 1.0 and advised_price != current_price:
            
            # --- Calculate Detailed Profit & Margin Attributes for the Ledger ---
            old_profit_dollars = current_price - cost_price
            old_margin_percent = (old_profit_dollars / current_price * 100) if current_price > 0 else 0.0
            
            new_profit_dollars = advised_price - cost_price
            new_margin_percent = (new_profit_dollars / advised_price * 100) if advised_price > 0 else 0.0

            change_record = {
                "product_id": p_id,
                "product_name": p_name,
                "stock_level": stock,
                "cost_price": cost_price,
                "current_price": current_price,
                "advised_price": advised_price,
                "old_profit_dollars": round(old_profit_dollars, 2),
                "old_margin_percent": round(old_margin_percent, 2),
                "new_profit_dollars": round(new_profit_dollars, 2),
                "new_margin_percent": round(new_margin_percent, 2),
                "profit_difference_dollars": round(new_profit_dollars - old_profit_dollars, 2),
                "margin_difference_percent": round(new_margin_percent - old_margin_percent, 2),
                "reason_code": reason_code,
                "simple_advice": advice 
            }
            advised_changes.append(change_record)

    # --- Step 3: Return Final Object ---
    return {
        "tenant_id": client_id,
        "meta": {
            "total_products_scanned": len(products_db),
            "products_requiring_action": len(advised_changes)
        },
        "advised_changes": advised_changes
    }