from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List
from app.core.security import verify_client
from app.core.database import get_db
from app.services.whale_hunter_engine import whale_hunter_engine

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
async def analyze_data(request: WhaleHunterRequest, db: dict = Depends(get_db)):
    # 1. Security & Service Check
    client_data = verify_client(request.client_id, request.client_pass, "whalehunter", db)
    
    # 2. Ensure Client Adapter URLs exist
    if not all(k in client_data for k in ("customers", "orders_api")):
        raise HTTPException(status_code=400, detail="Client missing required adapter URLs.")

    # 3. Trigger Engine
    try:
        # Pass the client's configuration and their ID to the engine
        report = await whale_hunter_engine(client_data, request.client_id)
        return report
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))