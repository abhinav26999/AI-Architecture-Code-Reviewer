import os
import logging
from typing import List, Dict
from fastapi import APIRouter, HTTPException, Query
from app.services.ingestion.cloner import repo_cloner, ClonerError
from app.services.parser.ast_parser import ast_parser
from app.api.routes.github import get_effective_installation_id
from app.schemas.parser import (
    ParserTestRequest,
    ParsedFile,
    ParseRepoRequest,
    ParseRepoResponse
)

router = APIRouter()
logger = logging.getLogger(__name__)

# Supported extensions
SUPPORTED_EXTENSIONS = {".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}


@router.post("/parse-file", response_model=ParsedFile)
async def parse_file(request: ParserTestRequest):
    """Parses a raw string of code and returns AST metadata (imports, classes, functions)."""
    # Create a dummy filename for extension mapping
    ext = ".py" if request.language.lower() == "python" else ".ts"
    dummy_filename = f"code_input{ext}"
    
    try:
        parsed_result = ast_parser.parse_code(request.code, dummy_filename)
        return parsed_result
    except Exception as e:
        logger.exception("Failed to parse code snippet")
        raise HTTPException(status_code=400, detail=f"Parsing error: {str(e)}")


@router.post("/parse-repo", response_model=ParseRepoResponse)
async def parse_repo(request: ParseRepoRequest):
    """
    Shallow clones a GitHub repository, parses all supported files,
    returns aggregated metadata, and cleans up the cloned repository folder.
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

    parsed_files: List[ParsedFile] = []
    parsing_errors: Dict[str, str] = {}
    total_files = 0

    # Directories to ignore
    ignored_dirs = {".git", "node_modules", "venv", ".venv", "__pycache__", "dist", "build"}

    # 2. Walk and parse files
    try:
        for root, dirs, files in os.walk(clone_path):
            # Modify dirs in-place to avoid traversing ignored directories
            dirs[:] = [d for d in dirs if d not in ignored_dirs]
            
            for file in files:
                ext = os.path.splitext(file)[1]
                if ext.lower() in SUPPORTED_EXTENSIONS:
                    total_files += 1
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, clone_path)
                    
                    try:
                        with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                            content = f.read()
                        
                        parsed = ast_parser.parse_code(content, rel_path)
                        parsed_files.append(parsed)
                    except Exception as e:
                        logger.error(f"Error parsing file {rel_path}: {e}")
                        parsing_errors[rel_path] = str(e)
                        
    finally:
        # 3. Cleanup cloned repository folder (Guaranteed execution)
        repo_cloner.cleanup_clone(clone_path)

    return ParseRepoResponse(
        owner=request.owner,
        repo=request.repo,
        total_files=total_files,
        parsed_files=parsed_files,
        parsing_errors=parsing_errors
    )
