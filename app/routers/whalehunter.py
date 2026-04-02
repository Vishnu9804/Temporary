from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List
from datetime import datetime
from app.services.whale_hunter_engine import analyze_tenant_data

router = APIRouter()

class Customer(BaseModel):
    customer_id: str
    account_created_at: datetime

class Order(BaseModel):
    order_id: str
    customer_id: str
    created_at: datetime
    total_amount: float
    discount_applied: float

class WhaleHunterRequest(BaseModel):
    tenant_id: str
    analysis_date: datetime = Field(default_factory=datetime.now)
    customers: List[Customer]
    orders: List[Order]

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
def analyze_data(payload: WhaleHunterRequest):
    if not payload.customers or not payload.orders:
        raise HTTPException(status_code=400, detail="Customers and orders arrays cannot be empty.")
    
    try:
        result = analyze_tenant_data(payload.dict())
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))