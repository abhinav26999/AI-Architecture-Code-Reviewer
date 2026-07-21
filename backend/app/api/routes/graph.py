import os
import logging
from typing import List, Dict
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
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


from fastapi import APIRouter, HTTPException, Request

# ...
@router.post("/analyze-repo", response_model=DependencyGraphResponse)
async def analyze_repo(request: ParseRepoRequest, raw_request: Request):
    """
    Shallow clones the repository, parses its codebase files,
    constructs the directed dependency graph, calculates instability/coupling metrics,
    finds circular dependency loops, and cleans up the cloned repository folder.
    """
    github_token = raw_request.headers.get("x-github-token")
    inst_id = None
    if not github_token:
        try:
            inst_id = await get_effective_installation_id(request.installation_id)
        except Exception:
            pass  # Fallback to PAT or public URL clone

    # 1. Clone repository
    try:
        clone_path = await repo_cloner.clone_repository(
            owner=request.owner,
            repo=request.repo,
            installation_id=inst_id,
            github_token=github_token
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


class PublicScanRequest(BaseModel):
    repo_url: str


@router.post("/scan-public", response_model=DependencyGraphResponse)
async def scan_public_graph(request: PublicScanRequest, raw_request: Request):
    """
    Analyzes the dependency graph of any public or private Git repository (GitHub, GitLab, Bitbucket) by URL.
    """
    github_token = raw_request.headers.get("x-github-token")
    gitlab_token = raw_request.headers.get("x-gitlab-token")
    bitbucket_token = raw_request.headers.get("x-bitbucket-token")

    # 1. Clone repository
    try:
        clone_path, owner, repo = await repo_cloner.clone_public_repository(
            repo_url=request.repo_url,
            github_token=github_token,
            gitlab_token=gitlab_token,
            bitbucket_token=bitbucket_token
        )
    except ClonerError as e:
        raise HTTPException(status_code=400, detail=str(e))

    parsed_files = []
    ignored_dirs = {".git", "node_modules", "venv", ".venv", "__pycache__", "dist", "build"}

    # 2. Parse codebase files
    try:
        for root, dirs, files in os.walk(clone_path):
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
                        logger.error(f"Error parsing file {rel_path} in public graph scan: {e}")
                        continue

        # 3. Build the dependency graph
        response = graph_builder.build_graph(
            owner=owner,
            repo=repo,
            parsed_files=parsed_files
        )
        return response

    finally:
        # 4. Clean up cloned codebase folder
        repo_cloner.cleanup_clone(clone_path)

