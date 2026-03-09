from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.core.security import verify_client
from app.services.return_engine import return_engine
from app.core.database import get_db

router = APIRouter()

# Define what the client MUST send you to trigger the CSI report
class ReturnCSIRequest(BaseModel):
    client_id: str
    client_pass: str

@router.post("/csi")
async def generate_return_csi(request: ReturnCSIRequest, db: dict = Depends(get_db)):
    # 1. Security Check (Verifies they exist, password is right, and they paid for "returns")
    client_data = verify_client(request.client_id, request.client_pass, "returns", db)
    
    # 2. Get their specific returns API endpoint from the DB
    returns_api_url = client_data.get("returns_api")
    if not returns_api_url:
        raise HTTPException(status_code=400, detail="Client does not have a returns_api configured.")

    # 3. Call the Service Logic
    csi_report = await return_engine(returns_api_url)
    
    return csi_report