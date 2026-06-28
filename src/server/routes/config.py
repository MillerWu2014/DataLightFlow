from __future__ import annotations

from fastapi import APIRouter, Request

from server.config_service import apply_config_update, config_to_response
from server.schemas import AppConfigResponse, AppConfigUpdate

router = APIRouter()


@router.get("/config", response_model=AppConfigResponse)
def get_config(request: Request) -> AppConfigResponse:
    config_path = request.app.state.settings.config_path
    return config_to_response(config_path)


@router.put("/config", response_model=AppConfigResponse)
def put_config(body: AppConfigUpdate, request: Request) -> AppConfigResponse:
    config_path = request.app.state.settings.config_path
    return apply_config_update(config_path, body)
