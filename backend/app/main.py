import time
import logging
from logging.handlers import RotatingFileHandler
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.routes import github, ingest, graph

# Configure Logging (Writes to backend/app.log and console)
log_file = "app.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        RotatingFileHandler(log_file, maxBytes=10000000, backupCount=5),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("app")

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Backend API for AI Architecture Code Reviewer",
    version="1.0.0",
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
)

# HTTP Request Logging Middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    path = request.url.path
    method = request.method
    client_host = request.client.host if request.client else "unknown"
    
    logger.info(f"Incoming Request: {method} {path} from {client_host}")
    
    try:
        response = await call_next(request)
        duration = (time.time() - start_time) * 1000
        logger.info(
            f"Request Success: {method} {path} | Status: {response.status_code} | Duration: {duration:.2f}ms"
        )
        return response
    except Exception as e:
        duration = (time.time() - start_time) * 1000
        logger.exception(
            f"Request Failed: {method} {path} | Error: {str(e)} | Duration: {duration:.2f}ms"
        )
        raise

# Set up CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(
    github.router,
    prefix=f"{settings.API_V1_STR}/github",
    tags=["github"],
)

app.include_router(
    ingest.router,
    prefix=f"{settings.API_V1_STR}/ingest",
    tags=["ingest"],
)

app.include_router(
    graph.router,
    prefix=f"{settings.API_V1_STR}/graph",
    tags=["graph"],
)


@app.get("/")
async def root():
    return {
        "project": settings.PROJECT_NAME,
        "status": "healthy",
        "docs_url": "/docs",
    }
