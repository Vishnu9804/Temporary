from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List
from app.core.security import verify_client
from app.core.database import get_db
from app.services.whale_hunter_engine import whale_hunter_engine
from sqlalchemy.orm import Session

router = APIRouter()

class WhaleHunterRequest(BaseModel):
    client_id: str
    client_pass: str

class ProcessingMeta(BaseModel):
    engine_used: str
    total_customers_received: int
    dead_pool_ignored: int
    active_customers_processed: int
    data_depth_days: int

class Segments(BaseModel):
    true_whales: List[str]
    at_risk_whales: List[str]
    deal_chasers: List[str]
    regulars: List[str]
    newbies: List[str]

class WhaleHunterResponse(BaseModel):
    tenant_id: str
    processing_meta: ProcessingMeta
    segments: Segments

@router.post("/analyze", response_model=WhaleHunterResponse)
async def analyze_data(request: WhaleHunterRequest, db: Session = Depends(get_db)):
    verify_client(request.client_id, request.client_pass, "whalehunter", db)
    report = await whale_hunter_engine(request.client_id, db)
    return report