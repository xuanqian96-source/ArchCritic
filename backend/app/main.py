"""应用入口，负责初始化服务、中间件和各类接口。"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.database import init_db
from app.routers import assets, auth, files, health, projects, submissions
from app.wiki import resolve_wiki_root


@asynccontextmanager
async def lifespan(_: FastAPI):
    """在应用启动时初始化数据库。"""
    init_db()
    yield


settings = get_settings()
local_dev_origins = {
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
    "http://localhost:4174",
    "http://127.0.0.1:4174",
}
configured_origins = {
    origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()
}

app = FastAPI(title=settings.app_name, version=settings.app_version, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(configured_origins | local_dev_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(assets.router)
app.include_router(projects.router)
app.include_router(submissions.router)
app.include_router(files.router)
app.mount(
    "/wiki-assets",
    StaticFiles(directory=resolve_wiki_root(settings.wiki_dir), check_dir=False),
    name="wiki-assets",
)
