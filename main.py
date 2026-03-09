from fastapi import FastAPI, Depends, HTTPException
from app.routers import chatbot, returns # <--- Imported returns here
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

# Include Return CSI Router <--- Added this block
app.include_router(
    returns.router,
    prefix=f"{settings.API_V1_STR}/returns", # This becomes "/api/v1/returns/csi"
    tags=["Returns CSI"]
)

# app.include_router(
#     pricing.router, 
#     prefix=f"{settings.API_V1_STR}/pricing", 
#     tags=["Pricing"]
# )