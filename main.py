from fastapi import FastAPI
from app.routers import chatbot, returnCSI, inventoryadvisor, associationbucketmaker, whalehunter # <--- ADDED IMPORT
from app.core.config import settings

app = FastAPI(title="My E-com B2B Startup")

@app.get("/")
def read_root():
    return {"status": "Service is running"}

app.include_router(chatbot.router, prefix=f"{settings.API_V1_STR}/chat", tags=["Chat"])
app.include_router(returnCSI.router, prefix=f"{settings.API_V1_STR}/returns", tags=["Returns CSI"])
app.include_router(inventoryadvisor.router, prefix=f"{settings.API_V1_STR}/inventory", tags=["Inventory Advisor"])

# ---> NEW SERVICE ADDED HERE
app.include_router(associationbucketmaker.router, prefix=f"{settings.API_V1_STR}/association", tags=["Association Bucket Maker"])

app.include_router(whalehunter.router, prefix=f"{settings.API_V1_STR}/whale-hunter", tags=["Whale Hunter"])