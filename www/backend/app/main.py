from pathlib import Path

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import FileResponse

from tg.router import router as telegram_router
from www.backend.app.settings import get_settings

settings = get_settings()
frontend_dir = Path(__file__).resolve().parents[2] / "frontend"

app = FastAPI(
    title="Kom_Dom_B",
    version="0.2.0-bootstrap",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
app.include_router(telegram_router)


@app.get("/")
def root() -> FileResponse:
    return FileResponse(frontend_dir / "index.html")


@app.get("/assets/{asset_name}")
def frontend_asset(asset_name: str) -> FileResponse:
    allowed_assets = {"app.js", "styles.css"}
    if asset_name not in allowed_assets:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return FileResponse(frontend_dir / asset_name)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.service_name}


@app.get("/ready")
def ready() -> dict[str, object]:
    return {
        "status": "bootstrap",
        "ready_for_traffic": False,
        "channels_enabled": settings.channels_enabled,
        "telegram_enabled": settings.telegram_enabled,
        "database_schema_applied": False,
    }


@app.post("/chat/api/external/")
def external_dialog_bootstrap_guard() -> None:
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "code": "business_pipeline_not_ready",
            "ready_for_traffic": False,
            "message": "Диалоговый цикл Kom_Dom_B ещё не введён в эксплуатацию.",
        },
    )
