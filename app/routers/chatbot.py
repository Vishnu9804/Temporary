from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.core.security import verify_client # Your Auth function
from app.services.chat_engine import generate_response

router = APIRouter()

# Define what the client MUST send you
class ChatRequest(BaseModel):
    client_id: str
    client_pass: str
    customer_id: str
    customer_msg: str

@router.post("/ask")
async def ask_chatbot(request: ChatRequest):
    # 1. Security Check (This queries your DB)
    is_valid = verify_client(request.client_id, request.client_pass, "chat")
    # if not is_valid:
    #     raise HTTPException(status_code=401, detail="Invalid Credentials")

    # 2. Call the Service Logic
    # We pass the client_id so the service knows WHICH client's data to look up
    bot_answer = await generate_response(request.client_id, request.customer_msg, request.customer_id)
    
    return {"response": bot_answer}