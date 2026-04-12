from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List
from app.core.security import verify_client
from app.core.database import get_db
from app.services.price_advisor_engine import price_advisor_engine
from sqlalchemy.orm import Session

router = APIRouter()

class PriceAdvisorRequest(BaseModel):
    client_id: str
    client_pass: str

class ProcessingMeta(BaseModel):
    total_products_scanned: int
    products_requiring_action: int

class AdvisedChange(BaseModel):
    product_id: str
    product_name: str
    stock_level: int
    cost_price: float
    current_price: float
    advised_price: float
    old_profit_dollars: float
    old_margin_percent: float
    new_profit_dollars: float
    new_margin_percent: float
    profit_difference_dollars: float
    margin_difference_percent: float
    reason_code: str
    simple_advice: str

class PriceAdvisorResponse(BaseModel):
    tenant_id: str
    meta: ProcessingMeta
    advised_changes: List[AdvisedChange]

@router.post("/analyze", response_model=PriceAdvisorResponse)
async def analyze_pricing(request: PriceAdvisorRequest, db: Session = Depends(get_db)):
    verify_client(request.client_id, request.client_pass, "priceadvisor", db)
    report = await price_advisor_engine(request.client_id, db)
    return report