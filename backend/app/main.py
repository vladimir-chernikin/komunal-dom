from fastapi import FastAPI, HTTPException, status

from app.settings import get_settings

settings = get_settings()

app = FastAPI(
    title="Kom_Dom_B",
    version="0.1.0-bootstrap",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


@app.get("/")
def root() -> dict[str, object]:
    return {
        "project": "Kom_Dom_B",
        "status": "bootstrap",
        "ready_for_traffic": False,
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.service_name}


@app.get("/ready")
def ready() -> dict[str, object]:
    return {
        "status": "bootstrap",
        "ready_for_traffic": False,
        "channels_enabled": settings.channels_enabled,
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
