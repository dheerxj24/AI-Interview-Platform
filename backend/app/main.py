from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .db import Base, engine
from .realtime import manager
from .realtime import router as realtime_router
from .routers import activity, problems, sessions


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    if settings.realtime_backend == "redis":
        await manager.start()
    yield
    if settings.realtime_backend == "redis":
        await manager.stop()


app = FastAPI(title="AI Interview Platform API", version="0.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(problems.router)
app.include_router(sessions.router)
app.include_router(activity.router)
app.include_router(realtime_router)


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok"}
