"""Dashboard API endpoints."""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import os

router = APIRouter(tags=["dashboard"])

# Get the directory containing static files
STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "dashboard")


@router.get("/", response_class=HTMLResponse)
async def dashboard_index(request: Request):
    """Serve the dashboard HTML."""
    file_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(file_path):
        with open(file_path, 'r') as f:
            content = f.read()
        return HTMLResponse(content=content)
    return HTMLResponse(content="<h1>Dashboard not found</h1>", status_code=404)


@router.get("/dashboard.js")
async def dashboard_script():
    """Serve the dashboard JavaScript."""
    file_path = os.path.join(STATIC_DIR, "dashboard.js")
    if os.path.exists(file_path):
        return FileResponse(file_path, media_type="application/javascript")
    return {"error": "File not found"}


@router.get("/mobile", response_class=HTMLResponse)
async def dashboard_mobile(request: Request):
    """Serve the mobile dashboard HTML."""
    file_path = os.path.join(STATIC_DIR, "mobile.html")
    if os.path.exists(file_path):
        with open(file_path, 'r') as f:
            content = f.read()
        return HTMLResponse(content=content)
    return HTMLResponse(content="<h1>Mobile dashboard not found</h1>", status_code=404)