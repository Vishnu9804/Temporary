from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.core.security import verify_client
from app.services.return_engine import return_engine
from app.core.database import get_db

router = APIRouter()

class ReturnCSIRequest(BaseModel):
    client_id: str
    client_pass: str

@router.post("/csi")
async def generate_return_csi(request: ReturnCSIRequest, db: Session = Depends(get_db)):
    verify_client(request.client_id, request.client_pass, "returns", db)
    
    # 3. Call the Service Logic using DB session directly
    csi_report = await return_engine(request.client_id, db)
    
    return csi_report