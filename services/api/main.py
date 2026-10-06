from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from services.api.incidents import (
    CsvInputError,
    analyze,
    load_records_from_text,
    results_csv_bytes,
    summary_for_api,
)
from services.api.routes.suppliers import router as suppliers_router
from services.api.routes.auth import router as auth_router
from services.api.routes.profiles import router as profiles_router
from services.api.routes.users import router as users_router
from services.api.security import CurrentUser


app = FastAPI(title="Nexova Incidents API", version="1.0.0")
app.include_router(suppliers_router)
app.include_router(auth_router)
app.include_router(profiles_router)
app.include_router(users_router)
latest_report_csv = None


@app.post("/api/incidents/analyze")
async def analyze_incidents(
    current_user: CurrentUser,
    file: UploadFile = File(...),
):
    global latest_report_csv

    filename = Path(file.filename or "").name
    if not filename or Path(filename).suffix.lower() != ".csv":
        raise HTTPException(status_code=415, detail="Selecciona un archivo con extensión .csv.")

    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="El archivo CSV está vacío.")
    try:
        rows = load_records_from_text(contents)
    except CsvInputError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    finally:
        await file.close()

    results = analyze(rows)
    summary = summary_for_api(results, "Archivo CSV")
    latest_report_csv = results_csv_bytes(results)
    return summary


@app.get("/api/incidents/results/report")
async def download_latest_report(current_user: CurrentUser):
    if latest_report_csv is None:
        raise HTTPException(
            status_code=404,
            detail="Todavía no hay un análisis disponible para descargar.",
        )
    return Response(
        content=latest_report_csv,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="results.csv"'},
    )


frontend_path = Path(__file__).resolve().parents[2] / "uis" / "backoffice"
app.mount("/", StaticFiles(directory=frontend_path, html=True), name="backoffice")