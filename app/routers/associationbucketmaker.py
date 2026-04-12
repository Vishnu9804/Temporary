from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.core.security import verify_client
from app.services.association_bucket_maker import association_engine
from app.core.database import get_db

router = APIRouter()

class AssociationRequest(BaseModel):
    client_id: str
    client_pass: str

@router.post("/generate")
async def generate_associations(request: AssociationRequest, db: Session = Depends(get_db)):
    verify_client(request.client_id, request.client_pass, "association", db)
    # Trigger Engine passing the DB session and client_id
    report = await association_engine(request.client_id, db)
    return report