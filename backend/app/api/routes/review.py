import os
import logging
from fastapi import APIRouter, HTTPException
from app.services.ingestion.cloner import repo_cloner, ClonerError
from app.services.parser.ast_parser import ast_parser
from app.services.dependency_graph.graph_builder import graph_builder
from app.services.rules.rule_engine import rule_engine
from app.api.routes.github import get_effective_installation_id
from app.services.github.github_client import github_client
from app.services.ai.ai_client import ai_client
from app.services.embeddings.rag_service import rag_service
from app.core.database import SessionLocal
from app.schemas.parser import ParseRepoRequest
from app.schemas.rules import ArchitectureReviewResponse
from pydantic import BaseModel
from typing import Optional

router = APIRouter()
logger = logging.getLogger(__name__)


class PRReviewRequest(BaseModel):
    owner: str
    repo: str
    pull_number: int
    installation_id: Optional[int] = None


class PublicScanRequest(BaseModel):
    repo_url: str


# Supported extensions
SUPPORTED_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
    ".go", ".rs", ".java", ".cpp", ".c", ".h", ".cs", ".php", ".swift", ".kt", ".dart"
}


@router.post("/analyze", response_model=ArchitectureReviewResponse)
async def analyze_codebase(request: ParseRepoRequest):
    """
    Performs a deterministic architectural review of the codebase.
    Clones the repository, parses it to extract imports and AST trees,
    computes the dependency graph, executes rule validations (N+1 queries,
    layer boundaries, blocking loops), cleans up cloned files, and returns results.
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

    # 2. Extract AST Metadata
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
                        logger.error(f"Error parsing file {rel_path} in review analyze: {e}")
                        continue

        # 3. Build Graph
        graph = graph_builder.build_graph(
            owner=request.owner,
            repo=request.repo,
            parsed_files=parsed_files
        )

        # 4. Run Rule Engine Checks
        review_results = await rule_engine.run_review(
            owner=request.owner,
            repo=request.repo,
            parsed_files=parsed_files,
            graph=graph,
            clone_path=clone_path
        )
        
        return review_results

    finally:
        # 5. Clean up cloned codebase folder (Guaranteed execution)
        repo_cloner.cleanup_clone(clone_path)


@router.post("/pr")
async def analyze_and_review_pr(request: PRReviewRequest):
    """
    Automated PR review pipeline.
    Fetches the pull request file changes/diffs from GitHub,
    clones and parses AST structures, builds the dependency graph,
    checks rule validations, queries pgvector RAG for historical outages,
    sends context to LLM reasoning, and posts the review comment to the PR.
    """
    try:
        inst_id = await get_effective_installation_id(request.installation_id)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Could not resolve active installation ID: {str(e)}"
        )

    # 1. Fetch changed files and diff patches from GitHub
    try:
        files = await github_client.get_pull_request_files(
            installation_id=inst_id,
            owner=request.owner,
            repo=request.repo,
            pull_number=request.pull_number
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch pull request files from GitHub: {str(e)}"
        )

    diffs_list = []
    for f in files:
        filename = f.get("filename", "")
        patch = f.get("patch", "")
        if patch:
            diffs_list.append(f"--- File: {filename}\n+++ File: {filename}\n{patch}")
    
    diffs_str = "\n\n".join(diffs_list) if diffs_list else "No code diffs found."

    # 2. Clone repository
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

    # 3. Extract AST Metadata
    try:
        for root, dirs, filenames in os.walk(clone_path):
            dirs[:] = [d for d in dirs if d not in ignored_dirs]
            
            for file in filenames:
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
                        logger.error(f"Error parsing file {rel_path} in PR review analyze: {e}")
                        continue

        # 4. Build Graph
        graph = graph_builder.build_graph(
            owner=request.owner,
            repo=request.repo,
            parsed_files=parsed_files
        )

        # 5. Run Rule Engine Checks
        review_results = await rule_engine.run_review(
            owner=request.owner,
            repo=request.repo,
            parsed_files=parsed_files,
            graph=graph,
            clone_path=clone_path
        )

        violations_messages = [v.message for v in review_results.violations]

        # 6. Query pgvector RAG for historical incident context matching the violations
        incidents_found = []
        try:
            async with SessionLocal() as db_session:
                for violation_msg in violations_messages:
                    similar = await rag_service.search_similar_incidents(
                        db=db_session,
                        query=violation_msg,
                        limit=2
                    )
                    for s in similar:
                        incidents_found.append(f"Title: {s.title}\nDescription: {s.description}")
        except Exception as e:
            logger.error(f"Failed to query RAG database in PR review: {e}")

        # 7. Generate AI Review comment
        review_comment = await ai_client.generate_pr_review(
            diffs=diffs_str,
            violations=violations_messages,
            related_incidents=incidents_found,
            score=review_results.score
        )

        # 8. Post review comment to GitHub PR
        try:
            await github_client.create_pull_request_review(
                installation_id=inst_id,
                owner=request.owner,
                repo=request.repo,
                pull_number=request.pull_number,
                body=review_comment
            )
            logger.info(f"PR review comment successfully posted to PR #{request.pull_number} on {request.owner}/{request.repo}")
        except Exception as e:
            logger.error(f"Failed to post PR review comment to GitHub: {e}")
            # Do not fail request, return successfully with the review body so user can inspect it
            return {
                "status": "partial_success",
                "message": f"PR analysis complete but failed to post review comment to GitHub: {str(e)}",
                "review_body": review_comment
            }

        return {
            "status": "success",
            "message": f"Architectural review comment posted to PR #{request.pull_number} successfully.",
            "review_body": review_comment
        }

    finally:
        # 9. Clean up cloned codebase folder (Guaranteed execution)
        repo_cloner.cleanup_clone(clone_path)


@router.post("/scan-public", response_model=ArchitectureReviewResponse)
async def scan_public_repository(request: PublicScanRequest):
    """
    Scans any public GitHub repository by URL. No authentication required.
    Clones the repo, parses files, builds graph, runs Rule Engine, and returns the review.
    """
    # 1. Clone public repository
    try:
        clone_path, owner, repo = await repo_cloner.clone_public_repository(request.repo_url)
    except ClonerError as e:
        raise HTTPException(status_code=400, detail=str(e))

    parsed_files = []
    ignored_dirs = {".git", "node_modules", "venv", ".venv", "__pycache__", "dist", "build"}

    # 2. Extract AST Metadata
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
                        logger.error(f"Error parsing file {rel_path} in public scan: {e}")
                        continue

        # 3. Build Graph
        graph = graph_builder.build_graph(
            owner=owner,
            repo=repo,
            parsed_files=parsed_files
        )

        # 4. Run Rule Engine Checks
        review_results = await rule_engine.run_review(
            owner=owner,
            repo=repo,
            parsed_files=parsed_files,
            graph=graph,
            clone_path=clone_path
        )

        return review_results

    finally:
        # 5. Clean up cloned codebase folder
        repo_cloner.cleanup_clone(clone_path)

