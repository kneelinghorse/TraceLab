"""FastAPI application entry point."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.database import engine, Base
from app.api.v1 import health, redaction, documents, retrieval

# Create tables in development (use migrations in production)
if settings.environment == "development":
    Base.metadata.create_all(bind=engine)

app = FastAPI(
    title=settings.app_name,
    description="Personal research repository with RAG-powered search",
    version=settings.app_version
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.environment == "development" else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router, prefix=settings.api_v1_prefix, tags=["health"])
app.include_router(redaction.router, prefix=f"{settings.api_v1_prefix}/redaction", tags=["redaction"])
app.include_router(documents.router, prefix=f"{settings.api_v1_prefix}/documents", tags=["documents"])
app.include_router(retrieval.router, prefix=f"{settings.api_v1_prefix}/retrieval", tags=["retrieval"])


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": settings.app_name,
        "version": settings.app_version,
        "status": "running"
    }
