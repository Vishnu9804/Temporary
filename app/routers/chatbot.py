from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.core.security import verify_client
from app.services.chat_engine import generate_response
from app.core.database import get_db

router = APIRouter()

class ChatRequest(BaseModel):
    client_id: str
    client_pass: str
    customer_id: str
    customer_msg: str

@router.post("/ask")
async def ask_chatbot(request: ChatRequest, db: Session = Depends(get_db)):
    # 1. Security Check
    verify_client(request.client_id, request.client_pass, "chat", db)

    # 2. Call the Service Logic (Now passing the db session)
    bot_answer = await generate_response(
        request.client_id, 
        request.customer_msg, 
        request.customer_id, 
        db
    )
    
    return bot_answer