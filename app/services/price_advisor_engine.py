import httpx
import asyncio
from typing import Dict, Any, List

async def price_advisor_engine(adapter_url: str, tenant_id: str) -> Dict[str, Any]:
    # --- Step 1: Fetch Data via Adapter ---
    async with httpx.AsyncClient() as client:
        resp = await client.get(adapter_url)
        if resp.status_code != 200:
            raise Exception("Failed to fetch data from client product adapter.")
        
        data_json = resp.json()
        
    products = data_json.get("products", []) if isinstance(data_json, dict) else data_json
    if not products:
        raise ValueError("Products array retrieved from adapter is empty.")

    advised_changes = []

    # --- Step 2: Analyze Business Logic (Competitors + Inventory Matrix) ---
    for p in products:
        p_id = p.get("id")
        p_name = p.get("name")
        current_price = float(p.get("price", 0.0))
        cost_price = float(p.get("cost_price", 0.0))  # Extracted from mock DB for profit calculation
        min_price = float(p.get("min_allowable_price", 0.0))
        stock = int(p.get("stock", 0))
        tags = p.get("core_matrix_tags", [])
        competitors = p.get("competitor_pricing_data", [])

        # 1. Dynamic Buffer Calculation
        is_premium = "Premium_Cosmetics" in tags
        buffer_percentage = 10.0 if is_premium else 5.0
        
        # 2. Competitor Status Grouping
        in_stock_comps = [c for c in competitors if c.get("is_in_stock", False)]
        out_of_stock_comps = [c for c in competitors if not c.get("is_in_stock", False)]

        target_price = current_price
        reason_code = "OPTIMAL"
        
        # Context variables for the static advice strings
        lowest_comp = None
        lowest_price = current_price
        names_str = ""

        # 3. Inventory-Aware Pricing Logic
        if in_stock_comps:
            # Find the absolute cheapest in-stock competitor
            lowest_comp = min(in_stock_comps, key=lambda x: float(x.get("observed_price", float('inf'))))
            lowest_price = float(lowest_comp.get("observed_price", current_price))
            
            if lowest_price < current_price:
                if stock < 50:
                    # SCARCITY: Don't chase the bottom. Protect margin because we have low stock.
                    target_price = current_price
                    reason_code = "SCARCITY_HOLD"
                elif stock > 500:
                    # OVERSTOCK: Aggressively match the lowest price to win the buy-box and clear inventory.
                    target_price = lowest_price
                    reason_code = "OVERSTOCK_PRICE_MATCH"
                else:
                    # NORMAL: Match the lower price.
                    target_price = lowest_price
                    reason_code = "PRICE_MATCH_REQUIRED"
        
        else:
            # No competitors are in stock
            if out_of_stock_comps:
                # Gather competitor names for the explanation
                oos_names = [c.get('competitor_name', 'Unknown') for c in out_of_stock_comps]
                names_str = ", ".join(oos_names[:3])
                if len(oos_names) > 3:
                    names_str += " and others"

                if stock < 50:
                    # MAXIMIZE MARGIN: Competitor is out, our stock is low. Premium Scarcity Pricing.
                    target_price = current_price * (1 + (buffer_percentage / 100))
                    reason_code = "COMPETITOR_OOS_SCARCITY_PREMIUM"
                elif stock > 500:
                    # VOLUME PLAY: Competitor is out, but we have tons of stock. Don't raise price, capture the volume.
                    target_price = current_price
                    reason_code = "COMPETITOR_OOS_HOLD_TO_CLEAR"
                else:
                    # NORMAL: Safely raise price by buffer
                    target_price = current_price * (1 + (buffer_percentage / 100))
                    reason_code = "COMPETITOR_OUT_OF_STOCK"
            else:
                # No competitors exist in the data
                if stock > 500:
                    # Proactive discounting on dead inventory
                    target_price = current_price * (1 - (buffer_percentage / 100))
                    reason_code = "OVERSTOCK_PROACTIVE_DISCOUNT"

        # 4. Margin Protection (Strict Rule)
        advised_price = max(target_price, min_price)
        advised_price = round(advised_price, 2)

        # --- Generate Simple Human-Readable Advice (10-Year-Old Friendly) ---
        advice = "Price is perfect, no changes needed right now."
        if reason_code == "SCARCITY_HOLD":
            advice = f"Keep the price at ${current_price:.2f}. Competitor '{lowest_comp['competitor_name']}' dropped their price to ${lowest_price:.2f}, but we only have {stock} left! Let's save them for buyers willing to pay our price."
        elif reason_code == "OVERSTOCK_PRICE_MATCH":
            if advised_price == min_price and min_price > lowest_price:
                 advice = f"Lower the price to ${advised_price:.2f}. Competitor '{lowest_comp['competitor_name']}' is selling at ${lowest_price:.2f}, but our allowed minimum is ${min_price:.2f}. We have too many ({stock} items), so drop it as low as safely possible to sell them fast."
            else:
                 advice = f"Lower the price to match '{lowest_comp['competitor_name']}' at ${advised_price:.2f}. We have way too many ({stock} items) taking up space! Let's sell them fast."
        elif reason_code == "PRICE_MATCH_REQUIRED":
            if advised_price == min_price and min_price > lowest_price:
                 advice = f"Lower the price to ${advised_price:.2f}. Competitor '{lowest_comp['competitor_name']}' is at ${lowest_price:.2f}, but we cannot go below our minimum cost of ${min_price:.2f}. Drop it as low as safely possible."
            else:
                 advice = f"Change the price to ${advised_price:.2f} to match '{lowest_comp['competitor_name']}'. If we don't match them, they will get all the sales!"
        elif reason_code == "COMPETITOR_OOS_SCARCITY_PREMIUM":
            advice = f"Raise the price to ${advised_price:.2f}! Competitors ({names_str}) are totally sold out. Since we only have {stock} left, people will pay extra to get it from us."
        elif reason_code == "COMPETITOR_OOS_HOLD_TO_CLEAR":
            advice = f"Keep the price at ${current_price:.2f}. Competitors ({names_str}) are sold out, and we have a huge pile ({stock} items). Keep the price exactly the same to grab all their customers and empty our shelves."
        elif reason_code == "COMPETITOR_OUT_OF_STOCK":
            advice = f"Raise the price to ${advised_price:.2f}! Competitors ({names_str}) ran out of this item. We can safely ask for more money because they have to buy from us."
        elif reason_code == "OVERSTOCK_PROACTIVE_DISCOUNT":
            advice = f"Put it on sale for ${advised_price:.2f}! We have way too many ({stock} items) just sitting there. Let's make it a little cheaper to convince people to buy it."

        # 5. Delta Threshold Check (Do we need to take action?)
        if current_price > 0:
            diff_percentage = (abs(current_price - advised_price) / current_price) * 100
        else:
            diff_percentage = 0.0

        if diff_percentage >= buffer_percentage and advised_price != current_price:
            
            # --- Calculate Detailed Profit & Margin Attributes ---
            old_profit_dollars = current_price - cost_price
            old_margin_percent = (old_profit_dollars / current_price * 100) if current_price > 0 else 0.0
            
            new_profit_dollars = advised_price - cost_price
            new_margin_percent = (new_profit_dollars / advised_price * 100) if advised_price > 0 else 0.0

            # Action needed! Prep the transparent record.
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
                "buffer_applied_percentage": buffer_percentage,
                "reason_code": reason_code,
                "simple_advice": advice 
            }
            advised_changes.append(change_record)

    # --- Step 3: Formatting and Return ---
    # The asyncio LLM gather step has been entirely removed as the advice is now perfectly pre-calculated
    return {
        "tenant_id": tenant_id,
        "meta": {
            "total_products_scanned": len(products),
            "products_requiring_action": len(advised_changes)
        },
        "advised_changes": advised_changes
    }