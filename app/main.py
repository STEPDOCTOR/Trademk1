from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.config.settings import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # TODO: Initialize database connection
    # TODO: Initialize Redis connection
    # TODO: Initialize other services
    print("Starting up...")
    yield
    # TODO: Close database connection
    # TODO: Close Redis connection
    # TODO: Cleanup other services
    print("Shutting down...")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version="0.1.0",
        lifespan=lifespan
    )
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    app.include_router(health_router, prefix="/api", tags=["health"])
    
    @app.get("/")
    async def root():
        return {"message": "Trademk1 API", "version": "0.1.0"}
    
    return app


app = create_app()