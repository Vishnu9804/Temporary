import google.generativeai as genai
import json
import os
from app.core.config import settings
import requests

# 1. Setup the Free Tier API
genai.configure(api_key=settings.API_KEY)

# We use the 'flash' model because it is lightning fast and great for chatbots
model = genai.GenerativeModel('gemini-2.5-flash')

async def generate_response(client_id: str, msg: str, customer_id: str):
    
    # ==========================================
    # STAGE 1: INTENT CLASSIFICATION & EXTRACTION
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
    - ALSO include 2-3 highly related, contextual keywords that would help find the right product. (e.g., if they ask for "dry skin", add "hydration, moisturizer". If they ask for "slim fit t-shirt", add "athletic fit, tight t-shirt").
    - Do NOT write full sentences for the keywords. Only use powerful search phrases.
    - If the category does not require a product search (like OrderTracking or ReturnStatus), leave the keyword section blank.

    Examples:
    User: "Suggest me some products for dry skin"
    Output: ProductSearch dry skin, hydration, moisturizer, hydrating serum
    
    User: "Which t shirts suit a slim body type?"
    Output: ProductSearch slim fit t-shirt, athletic fit, tight t-shirt
    
    User: "Where is my package?"
    Output: OrderTracking
    
    User: "What is the status of my refund?"
    Output: ReturnStatus

    User Message: "{msg}"
    """
    
    # Call the LLM to get the category and query
    llm_output = model.generate_content(classification_prompt).text.strip()
    
    # Split the response into the intent and the search string
    parts = llm_output.split(" ", 1)
    inquiry_type = parts[0]
    search_query = parts[1] if len(parts) > 1 else ""
    
    print(f"Detected Intent: {inquiry_type}") 
    if search_query:
        print(f"Extracted Keywords: {search_query}")

    # ==========================================
    # STAGE 2: FETCH API DATA & PRE-PROCESS
    # ==========================================
    
    resp = {} 
    extra_prompt_rules = "" 
    
    if inquiry_type in ["ProductSearch", "Discount"]:
        original_string = search_query
        # Split the comma-separated string into a list of individual search terms
        search_terms = [term.strip() for term in search_query.split(",") if term.strip()]
        
        all_found_products = []
        
        # Hit the search API for EVERY generated keyword
        for term in search_terms:
            search_api_url = f"http://127.0.0.1:8001/products/search?q={term}"
            search_resp = requests.get(search_api_url)
            
            if search_resp.status_code == 200:
                data = search_resp.json()
                
                if isinstance(data, list) and len(data) > 0:
                    all_found_products.extend(data)
                elif isinstance(data, dict):
                    if "products" in data and len(data["products"]) > 0:
                        all_found_products.extend(data["products"])
                    elif "items" in data and len(data["items"]) > 0:
                        all_found_products.extend(data["items"])

        # If no products were found across all search terms, return fallback
        if not all_found_products:
            return {
                "response": f"No products found for: {original_string}.",
                "response_type": "product_id",
                "product_id": []
            }
            
        # --- Deduplication and Frequency Sorting ---
        product_counts = {}
        product_map = {}
        
        for product in all_found_products:
            pid = product.get("id")
            if not pid:
                continue
                
            if pid in product_counts:
                product_counts[pid] += 1
            else:
                product_counts[pid] = 1
                product_map[pid] = product
                
        # Sort product IDs based on how many times they appeared (highest frequency first)
        sorted_pids = sorted(product_counts.keys(), key=lambda k: product_counts[k], reverse=True)
        
        # Build the final ordered list of unique products
        found_results = [product_map[pid] for pid in sorted_pids]
            
        # Assign to resp for the LLM
        resp = found_results
        
        if inquiry_type == "ProductSearch":
            extra_prompt_rules = "- Describe the products found clearly, including names and prices."
        else:
            extra_prompt_rules = "- Only include and describe products from the JSON that actually have a discount applied. Ignore products with 0 discount."

    elif inquiry_type == "OrderTracking":
        # 1. Fetch raw orders
        raw_orders_resp = requests.get(f"http://127.0.0.1:8001/orders?customer_id={customer_id}")
        
        # Handle potential API errors gracefully
        if raw_orders_resp.status_code == 200:
            raw_orders = raw_orders_resp.json()
            
            # 2. Sort orders chronologically (oldest to newest)
            sorted_orders = sorted(raw_orders, key=lambda x: x['created_at'])
            
            # 3. Enrich the orders with actual product names
            enriched_orders = []
            for order in sorted_orders:
                enriched_items = []
                
                for item in order.get("items", []):
                    product_id = item["product_id"]
                    
                    # Fetch product details for this specific item
                    prod_resp = requests.get(f"http://127.0.0.1:8001/products/{product_id}")
                    
                    # Default name if the product isn't found
                    product_name = product_id 
                    if prod_resp.status_code == 200:
                        product_data = prod_resp.json()
                        product_name = product_data.get("name", product_id) 
                        
                    enriched_items.append({
                        "product_name": product_name,
                        "quantity": item["quantity"]
                    })
                    
                # Build a clean dictionary for the LLM
                enriched_orders.append({
                    "order_id": order["id"],
                    "created_at": order["created_at"],
                    "status": order["status"],
                    "tracking_number": order["tracking_number"],
                    "items": enriched_items
                })
            
            resp = enriched_orders
            
            extra_prompt_rules = """
            - For each order in the JSON, format your response EXACTLY like this example: 
              "Order 1. (for next order increase the number) which was created at [Based on Date, answer like 1 January 2025]. Items in this order: [List of Product Names]. Tracking status: [based Status, answer in talkative way]."
            """
        else:
            resp = {"error": "Could not retrieve orders at this time."}
            
    elif inquiry_type == "CustomerInfo":
        resp = requests.get(f"http://127.0.0.1:8001/customers/{customer_id}").json()
    
    elif inquiry_type == "ReturnStatus":
        returns_resp = requests.get(f"http://127.0.0.1:8001/returns?customer_id={customer_id}")
        
        if returns_resp.status_code == 200:
            raw_returns = returns_resp.json()
            
            # The API returns them latest to oldest, which is perfect for returns.
            # Enrich the returns with actual product names
            enriched_returns = []
            for rma in raw_returns:
                enriched_items = []
                
                for item in rma.get("items", []):
                    product_id = item["product_id"]
                    
                    # Fetch product details for this specific item
                    prod_resp = requests.get(f"http://127.0.0.1:8001/products/{product_id}")
                    
                    product_name = product_id 
                    if prod_resp.status_code == 200:
                        product_data = prod_resp.json()
                        product_name = product_data.get("name", product_id) 
                        
                    enriched_items.append({
                        "product_name": product_name,
                        "quantity": item["quantity"],
                        "price": item.get("price")
                    })
                
                # Build a clean dictionary for the LLM
                enriched_returns.append({
                    "return_id": rma["id"],
                    "order_id": rma["order_id"],
                    "status": rma["status"],
                    "return_reason": rma["return_reason"],
                    "created_at": rma["created_at"],
                    "return_tracking_number": rma.get("return_tracking_number"),
                    "refund_amount": rma.get("refund_amount"),
                    "items": enriched_items
                })
            
            resp = enriched_returns
            
            extra_prompt_rules = """
            - For each return in the JSON clearly state the current status (e.g. 'refunded', 'in_transit') but in the human readable way (e.g. 'The return is currently in transit').
            - Mention the specific product names being returned and the refund amount dont mention any IDs.
            """
        else:
            resp = {"error": "Could not retrieve return status at this time."}
        
    # ... add your other elif blocks here ...

    # ==========================================
    # STAGE 3: GENERATE FINAL ANSWER (WITH ID EXTRACTION)
    # ==========================================
    
    generation_prompt = f"""
    You are an expert e-commerce customer support chatbot.
    Your task is to answer the user's message using ONLY the provided JSON data.
    
    CRITICAL OUTPUT FORMAT RULE:
    You must evaluate the JSON data against the User Message. Filter the data based on what the user is asking.
    Your output MUST be in this exact format:
    <Comma separated list of IDs for the items you are mentioning> @#@ <Your human-readable conversational answer>
    
    - If you are mentioning products, provide their product IDs.
    - If you are mentioning orders, provide their order IDs.
    - If you are mentioning returns, provide their return IDs (e.g., RMA-1001).
    - If there are no items that match the user's query in the JSON, output: none @#@ <Your polite apology>
    
    Strict Rules for the Conversational Answer:
    - Start your conversational answer immediately after the @#@ delimiter.
    - Do NOT use introductory phrases like "Here is the information."
    - Do NOT use concluding phrases like "Let me know if you need anything else."
    - Be polite, concise, and professional.
    {extra_prompt_rules}
    
    JSON Data: {json.dumps(resp)}
    
    User Message: "{msg}"
    """
    
    # Get the raw output which now includes the IDs and the @#@ delimiter
    raw_llm_output = model.generate_content(generation_prompt).text.strip()
    
    # Parse the LLM output into IDs and the actual chat response
    extracted_ids = []
    final_answer = raw_llm_output
    
    if "@#@" in raw_llm_output:
        parts = raw_llm_output.split("@#@", 1)
        id_string = parts[0].strip()
        final_answer = parts[1].strip()
        
        if id_string.lower() != "none" and id_string != "":
            # Replace commas with spaces, then split to ensure clean IDs without trailing commas
            extracted_ids = [i.strip() for i in id_string.replace(",", " ").split() if i.strip()]

    # ==========================================
    # STAGE 4: BUILD THE RETURN DICTIONARY
    # ==========================================
    
    result = {
        "response": final_answer,
        "response_type": "unknown"
    }
    
    # Inject the filtered IDs based on the intent
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