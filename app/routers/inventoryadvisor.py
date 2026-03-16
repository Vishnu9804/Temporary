from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.core.security import verify_client
from app.services.inventory_advisor import inventory_engine
from app.core.database import get_db

router = APIRouter()

class InventoryRequest(BaseModel):
    client_id: str
    client_pass: str

@router.post("/forecast")
async def generate_inventory_forecast(request: InventoryRequest, db: dict = Depends(get_db)):
    # 1. Security & Service Check
    client_data = verify_client(request.client_id, request.client_pass, "inventory", db)
    
    # 2. Ensure Client Adapter URLs exist
    if not all(k in client_data for k in ("orders_api", "products_api", "restocks_api")):
        raise HTTPException(status_code=400, detail="Client missing required adapter URLs.")

    # 3. Trigger Engine
    report = await inventory_engine(client_data)
    return report