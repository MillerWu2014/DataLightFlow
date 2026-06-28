from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from server.job_runner import JobRunner
from server.routes import config, jobs, sessions
from server.settings import ServerSettings
from server.storage import DataStore


def create_app(settings: ServerSettings | None = None) -> FastAPI:
    settings = settings or ServerSettings.load()
    store = DataStore(settings.data_dir)
    job_runner = JobRunner(store, settings.config_path)

    app = FastAPI(
        title="DataLight QA API",
        version="1.0.0",
        description="QA 数据工作台后端 API，对齐 ui/BACKEND_API.md",
    )
    app.state.settings = settings
    app.state.store = store
    app.state.job_runner = job_runner

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(jobs.router, prefix="/api/v1", tags=["jobs"])
    app.include_router(sessions.router, prefix="/api/v1", tags=["sessions"])
    app.include_router(config.router, prefix="/api/v1", tags=["config"])

    return app


app = create_app()
