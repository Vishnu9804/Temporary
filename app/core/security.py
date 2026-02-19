from fastapi import Depends, HTTPException, status
from app.core.database import get_db

# Notice: db is now just a standard Python Dictionary (dict)
def verify_client(client_id: str, client_pass: str, req_service: str, db: dict = Depends(get_db)):
    # 1. Check if client_id acts as a key in the dictionary
    if client_id not in db:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Client ID not found in JSON"
        )
    
    # 2. Get the client data
    client_data = db[client_id]

    # 3. Check password
    if client_data["password"] != client_pass:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect Password"
        )
    
    # 4. Check client opted for the requested service or not
    if req_service not in client_data["services"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You didnt opted for "+req_service
        )

    return client_data