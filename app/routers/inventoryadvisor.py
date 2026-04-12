from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.core.security import verify_client
from app.services.inventory_advisor import inventory_engine
from app.core.database import get_db

router = APIRouter()

class InventoryRequest(BaseModel):
    client_id: str
    client_pass: str

@router.post("/forecast")
async def generate_inventory_forecast(request: InventoryRequest, db: Session = Depends(get_db)):
    verify_client(request.client_id, request.client_pass, "inventory", db)
    report = await inventory_engine(request.client_id, db)
    return report