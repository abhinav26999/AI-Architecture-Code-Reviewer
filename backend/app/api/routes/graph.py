import os
import logging
from typing import List, Dict
from fastapi import APIRouter, HTTPException
from app.services.ingestion.cloner import repo_cloner, ClonerError
from app.services.parser.ast_parser import ast_parser
from app.services.dependency_graph.graph_builder import graph_builder
from app.api.routes.github import get_effective_installation_id
from app.schemas.parser import ParseRepoRequest
from app.schemas.graph import DependencyGraphResponse

router = APIRouter()
logger = logging.getLogger(__name__)

# Supported code extensions
SUPPORTED_EXTENSIONS = {".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}


@router.post("/analyze-repo", response_model=DependencyGraphResponse)
async def analyze_repo(request: ParseRepoRequest):
    """
    Shallow clones the repository, parses its codebase files,
    constructs the directed dependency graph, calculates instability/coupling metrics,
    finds circular dependency loops, and cleans up the cloned repository folder.
    """
    try:
        inst_id = await get_effective_installation_id(request.installation_id)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Could not resolve active installation ID: {str(e)}"
        )

    # 1. Clone repository
    try:
        clone_path = await repo_cloner.clone_repository(
            owner=request.owner,
            repo=request.repo,
            installation_id=inst_id
        )
    except ClonerError as e:
        raise HTTPException(status_code=500, detail=f"Repository ingestion failed: {str(e)}")

    parsed_files = []
    ignored_dirs = {".git", "node_modules", "venv", ".venv", "__pycache__", "dist", "build"}

    # 2. Parse codebase files to extract AST imports metadata
    try:
        for root, dirs, files in os.walk(clone_path):
            # Modify dirs in-place to avoid traversing ignored directories
            dirs[:] = [d for d in dirs if d not in ignored_dirs]
            
            for file in files:
                ext = os.path.splitext(file)[1]
                if ext.lower() in SUPPORTED_EXTENSIONS:
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, clone_path)
                    
                    try:
                        with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                            content = f.read()
                        
                        parsed = ast_parser.parse_code(content, rel_path)
                        parsed_files.append(parsed)
                    except Exception as e:
                        logger.error(f"Error parsing file {rel_path} in graph build: {e}")
                        # We continue parsing other files to be resilient
                        continue

        # 3. Compile and analyze the dependency graph
        response = graph_builder.build_graph(
            owner=request.owner,
            repo=request.repo,
            parsed_files=parsed_files
        )
        return response

    finally:
        # 4. Clean up cloned codebase folder from disk (Guaranteed execution)
        repo_cloner.cleanup_clone(clone_path)
