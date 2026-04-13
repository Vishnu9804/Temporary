import google.generativeai as genai
import json
from sqlalchemy.orm import Session
from app.models.schemas import ReturnRMA, Product
from app.core.config import settings

# Setup the API
genai.configure(api_key=settings.API_KEY)
model = genai.GenerativeModel('gemini-2.5-flash')

USELESS_COMMENTS = {
    "bad", "not good", "fake", "asdfgh", "terrible", 
    "poor", "waste", "hate it", "meh", "just no", "njdsndn"
}

async def return_engine(client_id: str, db: Session):
    # ==========================================
    # STAGE 1: FETCH RAW DATA FROM POSTGRES
    # ==========================================
    raw_returns = db.query(ReturnRMA).filter(ReturnRMA.client_id == client_id).all()

    # ==========================================
    # STAGE 2: STRICT SANITIZATION & GROUPING
    # ==========================================
    product_comments = {} 
    
    for rma in raw_returns:
        comment = rma.customer_comment
        reason = rma.return_reason or "Unknown"
        
        if comment is None:
            continue
        
        clean_comment = str(comment).strip().lower()
        if clean_comment == "" or clean_comment in USELESS_COMMENTS or len(clean_comment) < 3:
            continue
            
        items = rma.items or []
        for item in items:
            pid = item.get("product_id")
            if not pid: continue
            
            if pid not in product_comments:
                product_comments[pid] = []
            
            product_comments[pid].append({
                "reason": reason,
                "comment": str(comment).strip()
            })

    # ==========================================
    # STAGE 3: SORT & LIMIT (Max 10)
    # ==========================================
    sorted_products = sorted(product_comments.items(), key=lambda x: len(x[1]), reverse=True)
    top_products = sorted_products[:10]
    
    if not top_products:
        return {"message": "No valid return comments found after sanitization. System healthy."}

    # ==========================================
    # STAGE 4: ENRICH DATA & FORMAT FOR LLM
    # ==========================================
    llm_input_data = ""
    
    for rank, (pid, comments_list) in enumerate(top_products, 1):
        prod_name = pid
        # Fetch actual product name from database
        prod_db = db.query(Product).filter(Product.client_id == client_id, Product.id == pid).first()
        if prod_db and prod_db.name:
            prod_name = prod_db.name
        
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
        "core_issue": "1-3 word category (e.g., Packaging Failure, Sizing Issue)",
        "verdict": "A concise, 1-2 sentence final verdict of the exact problem.",
        "actionable_advice": "One clear, realistic recommendation for the business owner to fix it."
      }}
    ]
    """

    llm_output = model.generate_content(prompt).text.strip()
    
    if llm_output.startswith("```json"):
        llm_output = llm_output[7:]
    if llm_output.endswith("```"):
        llm_output = llm_output[:-3]
        
    try:
        structured_report = json.loads(llm_output.strip())
    except Exception as e:
        structured_report = {"raw_text": llm_output, "parsing_error": str(e)}

    return {
        "status": "success",
        "analyzed_products_count": len(top_products),
        "csi_report": structured_report
    }