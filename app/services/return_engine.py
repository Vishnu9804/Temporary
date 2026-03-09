import google.generativeai as genai
import requests
from app.core.config import settings

# 1. Setup the Free Tier API
genai.configure(api_key=settings.API_KEY)
model = genai.GenerativeModel('gemini-2.5-flash')

# The exact gibberish/lazy words we want to filter out
USELESS_COMMENTS = {
    "bad", "not good", "fake", "asdfgh", "terrible", 
    "poor", "waste", "hate it", "meh", "just no", "njdsndn"
}

async def analyze_returns(returns_api_url: str):
    # ==========================================
    # STAGE 1: FETCH RAW DATA
    # ==========================================
    try:
        resp = requests.get(returns_api_url)
        if resp.status_code != 200:
            return {"error": "Failed to fetch returns from client API."}
        
        raw_data = resp.json()
        # Handle if the API returns a list directly or a dict with a "returns" key
        raw_returns = raw_data.get("returns", raw_data) if isinstance(raw_data, dict) else raw_data
    except Exception as e:
        return {"error": f"API Connection Error: {str(e)}"}

    # ==========================================
    # STAGE 2: SANITIZE & GROUP (The Math Layer)
    # ==========================================
    product_comments = {} 
    
    for rma in raw_returns:
        comment = rma.get("customer_comment", "")
        reason = rma.get("return_reason", "Unknown")
        
        # 1. Drop completely blank or null comments
        if not comment or not str(comment).strip():
            continue
        
        clean_comment = str(comment).strip().lower()
        
        # 2. Drop gibberish and lazy single words
        if clean_comment in USELESS_COMMENTS or len(clean_comment) < 3:
            continue
            
        # 3. If it survived, group it by product_id
        items = rma.get("items", [])
        for item in items:
            pid = item.get("product_id")
            if not pid: continue
            
            if pid not in product_comments:
                product_comments[pid] = []
            
            product_comments[pid].append({
                "reason": reason,
                "comment": comment # Keep original casing for the LLM
            })

    # ==========================================
    # STAGE 3: SORT & LIMIT TO TOP 10
    # ==========================================
    # Sort products by the length of their valid comments array (Highest to lowest)
    sorted_products = sorted(product_comments.items(), key=lambda x: len(x[1]), reverse=True)
    
    # Slice the top 10 worst offenders
    top_10 = sorted_products[:10]
    
    if not top_10:
        return {"message": "No valid return comments found after sanitization. System healthy."}

    # ==========================================
    # STAGE 4: ENRICH DATA & FORMAT FOR LLM
    # ==========================================
    llm_input_data = ""
    
    for rank, (pid, comments_list) in enumerate(top_10, 1):
        # Fetch the real product name from the client's API
        prod_name = pid
        try:
            prod_resp = requests.get(f"http://127.0.0.1:8001/products/{pid}")
            if prod_resp.status_code == 200:
                prod_data = prod_resp.json()
                prod_name = prod_data.get("name", pid)
        except:
            pass # Fallback to just using the ID if API fails
        
        # Build the condensed string for the prompt
        llm_input_data += f"\nProductID: {pid} | ProductName: {prod_name}\n"
        for c in comments_list:
            llm_input_data += f"- Reason: {c['reason']} | Comment: {c['comment']}\n"

    # ==========================================
    # STAGE 5: THE LLM SNIPER
    # ==========================================
    prompt = f"""
    You are an expert E-commerce Quality Assurance Analyst.
    Below is the highly sanitized return data for the top most returned products. 
    
    {llm_input_data}

    Analyze the reasons and customer comments for each product to find the core underlying business issue (e.g., manufacturing defect, formula issue, packaging failure).

    CRITICAL OUTPUT FORMAT RULE:
    Do NOT include any conversational filler, greetings, or conclusions (No "Here is the analysis").
    Output your analysis strictly in this exact format for each product:

    ProductID: [Insert ID]
    ProductName: [Insert Name]
    Verdict: [A concise, 1-2 sentence final verdict and actionable analysis of the exact problem]

    ---
    """

    # Call the LLM
    llm_output = model.generate_content(prompt).text.strip()
    
    return {
        "status": "success",
        "analyzed_products_count": len(top_10),
        "csi_report": llm_output
    }