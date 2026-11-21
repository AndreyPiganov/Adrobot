from fastapi import FastAPI

from app.routers import campaigns

app = FastAPI(title="Adrobot API")
app.include_router(campaigns.router, prefix="/api")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
