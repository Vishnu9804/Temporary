from fastapi import requests

import google.generativeai as genai
import json
import os
from app.core.config import settings

# 1. Setup the Free Tier API
# Make sure you get your free API key from Google AI Studio and put it in your .env file
genai.configure(api_key=settings.GOOGLE_API_KEY)

# We use the 'flash' model because it is lightning fast and great for chatbots
model = genai.GenerativeModel('gemini-2.5-flash')

async def generate_response(client_id: str, msg: str, customer_id: str):
    
    # ==========================================
    # STAGE 1: INTENT CLASSIFICATION
    # ==========================================
    
    # Notice the strict rules in the prompt. This forces the LLM to behave like a router.
    classification_prompt = f"""
    You are a strict text classification engine. 
    Analyze the user's message and classify it into EXACTLY ONE of the following categories:
    - Comparison
    - Order Tracking
    - Product Search
    - Summarize Share
    - Cupon Code
    - Return Status
    - Customer Info
    - Unknown

    Rules:
    - Output ONLY the exact category name from the list above.
    - Do NOT output any punctuation, conversational text, or explanations.
    
    User Message: "{msg}"
    """
    
    # Call the LLM to get the category
    inquiry_type = model.generate_content(classification_prompt).text.strip()
    print(f"Detected Intent: {inquiry_type}") # Just so you can see it working
    
    # ==========================================
    # STAGE 2: FETCH API DATA
    # ==========================================
    
    resp = {} # This will hold the JSON from your client's API
    
    if inquiry_type == "Order Tracking":
        resp = requests.get(f"http://127.0.0.1:8001/orders?customer_id={customer_id}").json()
        # resp = {"status": "Out for delivery", "tracking_number": "FEDEX-123", "expected": "Today by 8PM"}
        
    elif inquiry_type == "Customer Info":
        # resp = fetch comparison API
        resp = requests.get(f"http://127.0.0.1:8001/customers/{customer_id}").json()
        # resp = {"product_a": "Cotton Shirt, $20", "product_b": "Linen Shirt, $35"}
        
    # ... add your other elif blocks here ...

    # ==========================================
    # STAGE 3: GENERATE FINAL ANSWER
    # ==========================================
    
    # Here we give the LLM the raw JSON data and tell it to format it nicely for the human.
    generation_prompt = f"""
    You are an expert e-commerce customer support chatbot.
    Your task is to answer the user's message using ONLY the provided JSON data.
    
    Strict Rules:
    - Start your answer immediately.
    - Do NOT use introductory phrases like "Here is the information," or "Based on the JSON provided."
    - Do NOT use concluding phrases like "Let me know if you need anything else."
    - Be polite, concise, and professional.
    
    JSON Data: {json.dumps(resp)}
    
    User Message: "{msg}"
    """
    
    # Get the final human-readable answer
    final_answer = model.generate_content(generation_prompt).text.strip()
    
    return final_answer

# # --- Let's test it! ---
# if __name__ == "__main__":
#     # Test 1: Order Tracking
#     answer1 = generate_response(
#         client_id="client_123", 
#         msg="Where is my stuff? I ordered it days ago.", 
#         customer_id="CUST-001"
#     )
#     print("\n--- Final Chatbot Answer ---")
#     print(answer1)