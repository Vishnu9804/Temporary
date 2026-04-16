import os

import google.generativeai as genai
import json
from sqlalchemy.orm import Session
from sqlalchemy import String, or_, cast
from app.models.schemas import Product, Order, Customer, ReturnRMA, ClientAuth
from app.core.config import settings

# Setup the API
genai.configure(api_key=settings.API_KEY)
model = genai.GenerativeModel('gemini-2.5-flash')

tax_path = os.path.join(os.path.dirname(__file__), '..', 'utils', 'universal_taxonomy.json')
try:
    with open(tax_path, 'r') as f:
        UNIVERSAL_TAXONOMY = json.load(f)
except FileNotFoundError:
    UNIVERSAL_TAXONOMY = {}

async def generate_response(client_id: str, msg: str, customer_id: str, db: Session):
    
    # Fetch Client Vertical to give the LLM the correct dictionary
    client_info = db.query(ClientAuth).filter(ClientAuth.client_id == client_id).first()
    vertical = client_info.vertical if client_info and client_info.vertical else "Cosmetics"
    
    # Get the specific dictionary for this client's industry
    client_dictionary = UNIVERSAL_TAXONOMY.get(vertical, {})

    customer_db = db.query(Customer).filter(Customer.client_id == client_id, Customer.id == customer_id).first()
    customer_context = {}
    if customer_db:
        customer_context = {
            "name": customer_db.name,
            "loyalty_tier": customer_db.loyalty_tier,
            "beauty_profile": customer_db.beauty_profile,
            "age": "info not available"  # Age is not stored, but LLM can infer from beauty profile if needed
        }
    customer_context_str = json.dumps(customer_context) if customer_context else "No specific customer profile available."
    
    # ==========================================
    # STAGE 1: INTENT & SYNCHRONIZED TAG EXTRACTION
    # ==========================================
    classification_prompt = f"""
    You are an intent classification and search query generator for a B2B SaaS platform serving a {vertical} business.
    Analyze the user's message and output a single line.
    
    Customer Profile Context: {customer_context_str}
    (Rule: Use this profile to guide search tags IF the user asks for generic recommendations. Do NOT restrict search tags to this profile if the user explicitly asks for something outside of their profile.)

    Format:
    <IntentCategory> <Comma-separated keywords>

    Categories: OrderTracking, ProductSearch, Discount, ReturnStatus, CustomerInfo, Unknown

    CRITICAL RULES FOR KEYWORDS (THE SYNC MECHANISM):
    If the intent is ProductSearch or Discount, you MUST translate the user's natural language into the exact tags used in our database. 
    Here is the exact dictionary of allowed tags for this business:
    {json.dumps(client_dictionary)}

    Do NOT invent words. If the user says "I need something that dries fast", look at the dictionary and map it to "fast-absorbing".
    Only output tags from the dictionary provided, plus the literal product name if they mentioned one.

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
        
        # Hit Postgres. We must use cast(..., String) to search inside JSONB arrays with ilike
        for term in search_terms:
            search_pattern = f"%{term}%"
            products_db = db.query(Product).filter(
                Product.client_id == client_id,
                or_(
                    Product.name.ilike(search_pattern),
                    Product.category.ilike(search_pattern),
                    Product.description.ilike(search_pattern),
                    cast(Product.core_matrix_tags, String).ilike(search_pattern),
                    cast(Product.key_ingredients, String).ilike(search_pattern),
                    cast(Product.tags, String).ilike(search_pattern)
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
                "response": f"No products found matching: {original_string}.",
                "response_type": "product_id",
                "product_id": []
            }
            
        # Deduplication and Frequency Sorting (Items that matched multiple tags float to the top)
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
        # Limit to top 5 best matches to avoid context overload
        resp = [product_map[pid] for pid in sorted_pids[:5]]
        
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