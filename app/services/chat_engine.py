import google.generativeai as genai
import json
from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.models.schemas import Product, Order, Customer, ReturnRMA
from app.core.config import settings

# Setup the API
genai.configure(api_key=settings.API_KEY)
model = genai.GenerativeModel('gemini-2.5-flash')

async def generate_response(client_id: str, msg: str, customer_id: str, db: Session):
    
    # ==========================================
    # STAGE 1: INTENT CLASSIFICATION
    # ==========================================
    classification_prompt = f"""
    You are an intent classification and intelligent search query generator for an e-commerce platform.
    Analyze the user's message and output a single line.
    
    Format:
    <IntentCategory> <Comma-separated list of highly relevant search keywords>

    Categories:
    - OrderTracking
    - ProductSearch
    - Discount
    - ReturnStatus
    - CustomerInfo
    - Unknown

    Rules for Keywords:
    - If the category is ProductSearch or Discount, generate a comma-separated list of concise search terms.
    - Include the direct keywords from the user's message.
    - ALSO include 2-3 highly related, contextual keywords that would help find the right product.
    - Do NOT write full sentences for the keywords. Only use powerful search phrases.
    - If the category does not require a product search, leave the keyword section blank.

    User Message: "{msg}"
    """
    
    llm_output = model.generate_content(classification_prompt).text.strip()
    parts = llm_output.split(" ", 1)
    inquiry_type = parts[0]
    search_query = parts[1] if len(parts) > 1 else ""

    # ==========================================
    # STAGE 2: FETCH DB DATA & PRE-PROCESS
    # ==========================================
    resp = {} 
    extra_prompt_rules = "" 
    
    if inquiry_type in ["ProductSearch", "Discount"]:
        original_string = search_query
        search_terms = [term.strip() for term in search_query.split(",") if term.strip()]
        
        all_found_products = []
        
        # Hit the PostgreSQL Database for EVERY keyword
        for term in search_terms:
            search_pattern = f"%{term}%"
            products_db = db.query(Product).filter(
                Product.client_id == client_id,
                or_(
                    Product.name.ilike(search_pattern),
                    Product.category.ilike(search_pattern),
                    Product.description.ilike(search_pattern)
                )
            ).all()
            
            for p in products_db:
                all_found_products.append({
                    "id": p.id,
                    "name": p.name,
                    "price": float(p.price),
                    "discount_percentage": float(p.discount_percentage or 0.0),
                    "description": p.description
                })

        if not all_found_products:
            return {
                "response": f"No products found for: {original_string}.",
                "response_type": "product_id",
                "product_id": []
            }
            
        # Deduplication and Frequency Sorting
        product_counts = {}
        product_map = {}
        for product in all_found_products:
            pid = product["id"]
            if pid in product_counts:
                product_counts[pid] += 1
            else:
                product_counts[pid] = 1
                product_map[pid] = product
                
        sorted_pids = sorted(product_counts.keys(), key=lambda k: product_counts[k], reverse=True)
        resp = [product_map[pid] for pid in sorted_pids]
        
        if inquiry_type == "ProductSearch":
            extra_prompt_rules = "- Describe the products found clearly, including names and prices."
        else:
            extra_prompt_rules = "- Only include and describe products from the JSON that actually have a discount applied. Ignore products with 0 discount."

    elif inquiry_type == "OrderTracking":
        orders_db = db.query(Order).filter(Order.client_id == client_id, Order.customer_id == customer_id).all()
        
        sorted_orders = sorted(orders_db, key=lambda x: x.created_at)
        enriched_orders = []
        
        for order in sorted_orders:
            enriched_items = []
            for item in order.items:
                product_id = item["product_id"]
                prod_db = db.query(Product).filter(Product.client_id == client_id, Product.id == product_id).first()
                product_name = prod_db.name if prod_db else product_id 
                    
                enriched_items.append({
                    "product_name": product_name,
                    "quantity": item["quantity"]
                })
                
            enriched_orders.append({
                "order_id": order.id,
                "created_at": order.created_at.isoformat(),
                "status": order.status,
                "tracking_number": order.tracking_number,
                "items": enriched_items
            })
        
        resp = enriched_orders
        extra_prompt_rules = "- For each order in the JSON, format your response EXACTLY like this example: 'Order 1 which was created at [Date]. Items in this order: [List of Product Names]. Tracking status: [Status].'"
            
    elif inquiry_type == "CustomerInfo":
        cust_db = db.query(Customer).filter(Customer.client_id == client_id, Customer.id == customer_id).first()
        if cust_db:
            resp = {
                "id": cust_db.id,
                "name": cust_db.name,
                "email": cust_db.email,
                "loyalty_tier": cust_db.loyalty_tier
            }
        else:
            resp = {"error": "Customer data not found."}
    
    elif inquiry_type == "ReturnStatus":
        returns_db = db.query(ReturnRMA).filter(ReturnRMA.client_id == client_id, ReturnRMA.customer_id == customer_id).all()
        
        enriched_returns = []
        for rma in returns_db:
            enriched_items = []
            for item in rma.items:
                product_id = item["product_id"]
                prod_db = db.query(Product).filter(Product.client_id == client_id, Product.id == product_id).first()
                product_name = prod_db.name if prod_db else product_id 
                    
                enriched_items.append({
                    "product_name": product_name,
                    "quantity": item["quantity"],
                    "price": item.get("price")
                })
            
            enriched_returns.append({
                "return_id": rma.id,
                "order_id": rma.order_id,
                "status": rma.status,
                "return_reason": rma.return_reason,
                "created_at": rma.created_at.isoformat(),
                "items": enriched_items
            })
        
        resp = enriched_returns
        extra_prompt_rules = "- For each return clearly state the current status in a human readable way. Mention the specific product names being returned, don't mention any IDs."

    # ==========================================
    # STAGE 3: GENERATE FINAL ANSWER 
    # ==========================================
    generation_prompt = f"""
    You are an expert e-commerce customer support chatbot.
    Your task is to answer the user's message using ONLY the provided JSON data.
    
    CRITICAL OUTPUT FORMAT RULE:
    Your output MUST be in this exact format:
    <Comma separated list of IDs for the items you are mentioning> @#@ <Your human-readable conversational answer>
    
    - If you are mentioning products, provide their product IDs.
    - If you are mentioning orders, provide their order IDs.
    - If you are mentioning returns, provide their return IDs.
    - If there are no items that match, output: none @#@ <Your polite apology>
    
    Strict Rules:
    - Start conversational answer immediately after @#@.
    - Be polite, concise, and professional.
    {extra_prompt_rules}
    
    JSON Data: {json.dumps(resp)}
    
    User Message: "{msg}"
    """
    
    raw_llm_output = model.generate_content(generation_prompt).text.strip()
    
    extracted_ids = []
    final_answer = raw_llm_output
    
    if "@#@" in raw_llm_output:
        parts = raw_llm_output.split("@#@", 1)
        id_string = parts[0].strip()
        final_answer = parts[1].strip()
        
        if id_string.lower() != "none" and id_string != "":
            extracted_ids = [i.strip() for i in id_string.replace(",", " ").split() if i.strip()]

    # ==========================================
    # STAGE 4: BUILD THE RETURN DICTIONARY
    # ==========================================
    result = {
        "response": final_answer,
        "response_type": "unknown"
    }
    
    if inquiry_type in ["ProductSearch", "Discount"]:
        result["response_type"] = "product_id"
        result["product_id"] = extracted_ids
    elif inquiry_type == "OrderTracking":
        result["response_type"] = "order_id"
        result["order_id"] = extracted_ids
    elif inquiry_type == "ReturnStatus":
        result["response_type"] = "return_id"
        result["return_id"] = extracted_ids
            
    return result