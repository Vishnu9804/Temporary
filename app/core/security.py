from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.schemas import ClientAuth

def verify_client(client_id: str, client_pass: str, req_service: str, db: Session):
    # 1. Query the DB for the client
    client = db.query(ClientAuth).filter(ClientAuth.client_id == client_id).first()
    
    if not client:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Client ID not found: {client_id}"
        )
    
    # 2. Check password
    if client.password != client_pass:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect Password"
        )
    
    # 3. Check client opted for the requested service or not
    if req_service not in client.services:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"You didn't opt for {req_service}"
        )

    return client