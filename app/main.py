import logging
from fastapi import FastAPI
from app.api.auth import router as auth_router
from app.api.users import router as users_router
from app.api.documents import router as documents_router


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)


app = FastAPI(
    title="AI_PDF",
    description="AI PDF Document Analyzer",
    version="1.0.0",
)

app.include_router(auth_router)
app.include_router(users_router)
app.include_router(documents_router)
