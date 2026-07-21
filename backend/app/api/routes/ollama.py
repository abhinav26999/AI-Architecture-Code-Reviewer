import logging
import asyncio
import httpx
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel
from app.core.config import settings

router = APIRouter()
logger = logging.getLogger(__name__)


class RecommendedModelInfo(BaseModel):
    name: str
    description: str
    pull_command: str
    category: str  # "reasoning" | "coding" | "embedding"


class InstalledModelInfo(BaseModel):
    name: str
    size_mb: float
    parameter_size: Optional[str] = None
    family: Optional[str] = None
    modified_at: Optional[str] = None


class OllamaModelsResponse(BaseModel):
    status: str  # "online" | "offline"
    ollama_url: str
    total_installed_models: int
    default_env_model: str
    installed_models: List[InstalledModelInfo]
    recommended_models: List[RecommendedModelInfo]
    suggested_pull_commands: List[str]
    message: Optional[str] = None


class PullModelRequest(BaseModel):
    model_name: str
    ollama_url: Optional[str] = None


RECOMMENDED_MODELS: List[RecommendedModelInfo] = [
    RecommendedModelInfo(
        name="qwen2.5-coder",
        description="Alibaba Qwen 2.5 Coder - State-of-the-art open coding & architectural analysis model",
        pull_command="ollama pull qwen2.5-coder",
        category="coding"
    ),
    RecommendedModelInfo(
        name="llama3",
        description="Meta Llama 3 8B - Standard high-performance reasoning model for code critique",
        pull_command="ollama pull llama3",
        category="reasoning"
    ),
    RecommendedModelInfo(
        name="deepseek-r1:8b",
        description="DeepSeek R1 8B - Deep chain-of-thought reasoning for complex software architecture",
        pull_command="ollama pull deepseek-r1:8b",
        category="reasoning"
    ),
    RecommendedModelInfo(
        name="mistral",
        description="Mistral 7B - Fast & accurate general coding and refactoring assistant",
        pull_command="ollama pull mistral",
        category="coding"
    ),
    RecommendedModelInfo(
        name="nomic-embed-text",
        description="Nomic Embed Text - High performance local embedding model for RAG vector index",
        pull_command="ollama pull nomic-embed-text",
        category="embedding"
    ),
]


def resolve_base_url(raw_url: Optional[str] = None) -> str:
    """Extracts base host URL (e.g. http://localhost:11434) from generation or input URL."""
    url = raw_url.strip() if raw_url and raw_url.strip() else settings.OLLAMA_GEN_URL
    if "/api/" in url:
        url = url.split("/api/")[0]
    return url.rstrip("/")


@router.get("/models", response_model=OllamaModelsResponse)
async def list_ollama_models(
    ollama_url: Optional[str] = Query(None, description="Custom Ollama host URL (e.g., http://localhost:11434)")
):
    """
    Proxy endpoint to query local Ollama system models safely from backend.
    Returns count of installed models, installed model details, default model configured in .env,
    and recommended models to install.
    """
    base_url = resolve_base_url(ollama_url)
    tags_url = f"{base_url}/api/tags"

    suggested_commands = [m.pull_command for m in RECOMMENDED_MODELS]

    try:
        async with httpx.AsyncClient() as client:
            res = await client.get(tags_url, timeout=4.0)
            if res.status_code == 200:
                data = res.json()
                raw_models = data.get("models", [])
                
                installed: List[InstalledModelInfo] = []
                for m in raw_models:
                    details = m.get("details", {})
                    size_bytes = m.get("size", 0)
                    size_mb = round(size_bytes / (1024 * 1024), 2)
                    
                    installed.append(
                        InstalledModelInfo(
                            name=m.get("name", "unknown"),
                            size_mb=size_mb,
                            parameter_size=details.get("parameter_size"),
                            family=details.get("family"),
                            modified_at=m.get("modified_at")
                        )
                    )

                return OllamaModelsResponse(
                    status="online",
                    ollama_url=base_url,
                    total_installed_models=len(installed),
                    default_env_model=settings.OLLAMA_GEN_MODEL,
                    installed_models=installed,
                    recommended_models=RECOMMENDED_MODELS,
                    suggested_pull_commands=suggested_commands,
                    message=f"Local Ollama online with {len(installed)} installed models."
                )
            else:
                return OllamaModelsResponse(
                    status="offline",
                    ollama_url=base_url,
                    total_installed_models=0,
                    default_env_model=settings.OLLAMA_GEN_MODEL,
                    installed_models=[],
                    recommended_models=RECOMMENDED_MODELS,
                    suggested_pull_commands=suggested_commands,
                    message=f"Ollama returned HTTP status {res.status_code} at {tags_url}"
                )
    except Exception as e:
        logger.warning(f"Failed to query local Ollama at {tags_url}: {e}")
        return OllamaModelsResponse(
            status="offline",
            ollama_url=base_url,
            total_installed_models=0,
            default_env_model=settings.OLLAMA_GEN_MODEL,
            installed_models=[],
            recommended_models=RECOMMENDED_MODELS,
            suggested_pull_commands=suggested_commands,
            message=f"Ollama server unreachable at {base_url}. Verify Ollama is running locally."
        )


@router.post("/pull")
async def pull_ollama_model(request: PullModelRequest):
    """
    Triggers an automated download/pull of an Ollama model locally.
    Uses Ollama's HTTP API /api/pull or falls back to Ollama CLI subprocess execution.
    """
    base_url = resolve_base_url(request.ollama_url)
    pull_api_url = f"{base_url}/api/pull"
    clean_model_name = request.model_name.strip()

    logger.info(f"Initiating automatic model pull for '{clean_model_name}' at {base_url}...")

    # 1. Try Ollama HTTP API endpoint /api/pull
    try:
        async with httpx.AsyncClient() as client:
            res = await client.post(
                pull_api_url,
                json={"name": clean_model_name, "stream": False},
                timeout=600.0  # 10 minutes timeout for model download
            )
            if res.status_code == 200:
                logger.info(f"Successfully pulled model '{clean_model_name}' via Ollama HTTP API.")
                return {
                    "status": "success",
                    "model": clean_model_name,
                    "message": f"Model '{clean_model_name}' downloaded successfully!"
                }
    except Exception as e:
        logger.warning(f"Ollama HTTP /api/pull failed/timed out: {e}. Falling back to terminal CLI subprocess...")

    # 2. Subprocess fallback CLI `ollama pull <clean_model_name>`
    try:
        cmd = ["ollama", "pull", clean_model_name]
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        if process.returncode == 0:
            logger.info(f"Successfully pulled model '{clean_model_name}' via CLI subprocess.")
            return {
                "status": "success",
                "model": clean_model_name,
                "message": f"Model '{clean_model_name}' downloaded successfully!"
            }
        else:
            err_msg = stderr.decode().strip()
            logger.error(f"Failed to pull model '{clean_model_name}' via CLI: {err_msg}")
            raise HTTPException(status_code=500, detail=f"Ollama pull failed: {err_msg}")
    except Exception as e:
        if isinstance(e, HTTPException):
            raise
        logger.exception(f"Unexpected error pulling model '{clean_model_name}'")
        raise HTTPException(status_code=500, detail=f"Failed to pull model: {str(e)}")
