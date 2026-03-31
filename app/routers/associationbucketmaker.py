from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.core.security import verify_client
from app.services.association_bucket_maker import association_engine
from app.core.database import get_db

router = APIRouter()

class AssociationRequest(BaseModel):
    client_id: str
    client_pass: str

@router.post("/generate")
async def generate_associations(request: AssociationRequest, db: dict = Depends(get_db)):
    # 1. Security & Service Check
    client_data = verify_client(request.client_id, request.client_pass, "association", db)
    
    # 2. Ensure Client Adapter URLs exist
    if not all(k in client_data for k in ("orders_api", "products_api")):
        raise HTTPException(status_code=400, detail="Client missing required adapter URLs.")

    # 3. Trigger Engine
    report = await association_engine(client_data)
    
    # Currently returning straight to the user as requested
    return report