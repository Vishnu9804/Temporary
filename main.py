from fastapi import FastAPI, Depends, HTTPException
from app.routers import chatbot
from app.core.security import verify_client
from app.core.config import settings

app = FastAPI(title="My E-com B2B Startup")

# Basic health check
@app.get("/")
def read_root():
    return {"status": "Service is running"}

# Include your routers
# verify_client acts as a global guard for these routes if needed, 
# or you can put it inside the routers specific files.
app.include_router(
    chatbot.router, 
    prefix=f"{settings.API_V1_STR}/chat",  # This becomes "/api/v1/chat"
    tags=["Chat"]
)

# app.include_router(
#     pricing.router, 
#     prefix=f"{settings.API_V1_STR}/pricing", # This becomes "/api/v1/pricing"
#     tags=["Pricing"]
# )
# ... add others here