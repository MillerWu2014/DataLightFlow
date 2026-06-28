from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from datalight.config import DatalightConfig


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class ServerSettings:
    config_path: Path
    data_dir: Path
    max_upload_bytes: int
    cors_origins: list[str]

    @classmethod
    def load(cls) -> ServerSettings:
        config_path = Path(os.environ.get("DATALIGHT_CONFIG", _repo_root() / "configs" / "datalight.yaml"))
        app_cfg = DatalightConfig.from_file(config_path) if config_path.is_file() else DatalightConfig()
        default_data = (app_cfg.output.root or Path(".output")) / ".datalight-server"
        data_dir = Path(os.environ.get("DATALIGHT_SERVER_DATA", default_data))
        max_upload = int(os.environ.get("DATALIGHT_MAX_UPLOAD_MB", "32")) * 1024 * 1024
        origins_raw = os.environ.get("DATALIGHT_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
        cors_origins = [item.strip() for item in origins_raw.split(",") if item.strip()]
        return cls(
            config_path=config_path,
            data_dir=data_dir,
            max_upload_bytes=max_upload,
            cors_origins=cors_origins,
        )
