from fastapi import FastAPI, Depends, HTTPException
from app.routers import chatbot, returnCSI  # Fixed: Importing the correct filename
from app.core.security import verify_client
from app.core.config import settings

app = FastAPI(title="My E-com B2B Startup")

# Basic health check
@app.get("/")
def read_root():
    return {"status": "Service is running"}

# Include Chatbot Router
app.include_router(
    chatbot.router, 
    prefix=f"{settings.API_V1_STR}/chat",
    tags=["Chat"]
)

# Include Return CSI Router
app.include_router(
    returnCSI.router,
    prefix=f"{settings.API_V1_STR}/returns", 
    tags=["Returns CSI"]
)