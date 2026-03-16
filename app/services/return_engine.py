import google.generativeai as genai
import requests
import json
from app.core.config import settings

# 1. Setup the Free Tier API
genai.configure(api_key=settings.API_KEY)
model = genai.GenerativeModel('gemini-2.5-flash')

# The exact gibberish/lazy words we want to filter out
USELESS_COMMENTS = {
    "bad", "not good", "fake", "asdfgh", "terrible", 
    "poor", "waste", "hate it", "meh", "just no", "njdsndn"
}

async def return_engine(returns_api_url: str):
    # ==========================================
    # STAGE 1: FETCH RAW DATA
    # ==========================================
    try:
        resp = requests.get(returns_api_url)
        if resp.status_code != 200:
            return {"error": "Failed to fetch returns from client API."}
        
        raw_data = resp.json()
        # Handles your specific JSON structure seamlessly
        raw_returns = raw_data.get("returns", raw_data) if isinstance(raw_data, dict) else raw_data
    except Exception as e:
        return {"error": f"API Connection Error: {str(e)}"}

    # ==========================================
    # STAGE 2: STRICT SANITIZATION & GROUPING
    # ==========================================
    product_comments = {} 
    
    for rma in raw_returns:
        # Default to None if the key doesn't even exist
        comment = rma.get("customer_comment", None)
        reason = rma.get("return_reason", "Unknown")
        
        # 1. Drop explicitly null/None comments immediately
        if comment is None:
            continue
        
        # 2. Strip whitespaces and make lowercase for validation
        clean_comment = str(comment).strip().lower()
        
        # 3. Drop completely empty strings (this catches "" and "   ")
        if clean_comment == "":
            continue
        
        # 4. Drop gibberish and lazy single words
        if clean_comment in USELESS_COMMENTS or len(clean_comment) < 3:
            continue
            
        # 5. Group by product_id (Only the high-signal survivors make it here)
        items = rma.get("items", [])
        for item in items:
            pid = item.get("product_id")
            if not pid: continue
            
            if pid not in product_comments:
                product_comments[pid] = []
            
            product_comments[pid].append({
                "reason": reason,
                # We pass the original cased comment to the LLM, but stripped of trailing/leading spaces
                "comment": str(comment).strip()
            })

    # ==========================================
    # STAGE 3: SORT & LIMIT (Max 10)
    # ==========================================
    # Sort products by volume of valid complaints
    sorted_products = sorted(product_comments.items(), key=lambda x: len(x[1]), reverse=True)
    
    # Slice limits it to a maximum of 10. If there are only 3, it safely takes just those 3.
    top_products = sorted_products[:10]
    
    if not top_products:
        return {"message": "No valid return comments found after sanitization. System healthy."}

    # ==========================================
    # STAGE 4: ENRICH DATA & FORMAT FOR LLM
    # ==========================================
    llm_input_data = ""
    
    for rank, (pid, comments_list) in enumerate(top_products, 1):
        prod_name = pid
        try:
            prod_resp = requests.get(f"http://127.0.0.1:8001/products/{pid}")
            if prod_resp.status_code == 200:
                prod_data = prod_resp.json()
                prod_name = prod_data.get("name", pid)
        except:
            pass 
        
        llm_input_data += f"\nProductID: {pid} | ProductName: {prod_name}\n"
        for c in comments_list:
            llm_input_data += f"- Reason: {c['reason']} | Comment: {c['comment']}\n"

    # ==========================================
    # STAGE 5: THE STRUCTURED LLM SNIPER
    # ==========================================
    prompt = f"""
    You are an expert E-commerce Quality Assurance Analyst.
    Below is the highly sanitized return data for the most problematic products. 
    
    {llm_input_data}

    Analyze the reasons and customer comments for each product to find the core underlying business issue.

    CRITICAL OUTPUT FORMAT RULE:
    You MUST output a strict, valid JSON array of objects. 
    Do NOT include any conversational filler. Do NOT include markdown code blocks like ```json.
    
    Format your response EXACTLY like this array structure:
    [
      {{
        "product_id": "Insert ID",
        "product_name": "Insert Name",
        "core_issue": "1-3 word category (e.g., Packaging Failure, Sizing Issue, Oxidation)",
        "verdict": "A concise, 1-2 sentence final verdict of the exact problem.",
        "actionable_advice": "One clear, realistic recommendation for the business owner to fix it."
      }}
    ]
    """

    # Call the LLM
    llm_output = model.generate_content(prompt).text.strip()
    
    # Strip markdown if Gemini attempts to inject it
    if llm_output.startswith("```json"):
        llm_output = llm_output[7:]
    if llm_output.endswith("```"):
        llm_output = llm_output[:-3]
        
    # Safely convert the LLM string into actual Python dictionaries
    try:
        structured_report = json.loads(llm_output.strip())
    except Exception as e:
        # Fallback if the LLM breaks the JSON rules
        structured_report = {"raw_text": llm_output, "parsing_error": str(e)}

    return {
        "status": "success",
        "analyzed_products_count": len(top_products),
        "csi_report": structured_report
    }