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


class FixSuggestionRequest(BaseModel):
    rule_name: str
    message: str
    file_path: str
    severity: Optional[str] = "HIGH"
    suggested_fix: Optional[str] = None
    code_snippet: Optional[str] = None
    provider: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None
    ollama_url: Optional[str] = None


# Supported extensions
SUPPORTED_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
    ".go", ".rs", ".java", ".cpp", ".c", ".h", ".cs", ".php", ".swift", ".kt", ".dart"
}


@router.post("/analyze", response_model=ArchitectureReviewResponse)
async def analyze_codebase(request: ParseRepoRequest, raw_request: Request):
    """
    Performs a deterministic architectural review of the codebase.
    Clones the repository, parses it to extract imports and AST trees,
    computes the dependency graph, executes rule validations (N+1 queries,
    layer boundaries, blocking loops), cleans up cloned files, and returns results.
    """
    github_token = raw_request.headers.get("x-github-token")
    inst_id = None
    if not github_token:
        try:
            inst_id = await get_effective_installation_id(request.installation_id)
        except Exception:
            pass  # Fallback to token or public clone

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


from fastapi import APIRouter, HTTPException, Request

# ... inside analyze_and_review_pr:
@router.post("/pr")
async def analyze_and_review_pr(request: PRReviewRequest, raw_request: Request):
    """
    Automated PR review pipeline.
    Fetches the pull request file changes/diffs from GitHub,
    clones and parses AST structures, builds the dependency graph,
    checks rule validations, queries pgvector RAG for historical outages,
    sends context to LLM reasoning, and posts the review comment to the PR.
    """
    # Extract optional dynamic LLM headers
    llm_provider = raw_request.headers.get("x-llm-provider")
    openai_key = raw_request.headers.get("x-openai-key")
    gemini_key = raw_request.headers.get("x-gemini-key")
    ollama_model = raw_request.headers.get("x-ollama-model")
    ollama_url = raw_request.headers.get("x-ollama-url")
    
    api_key = openai_key if llm_provider == "openai" else (gemini_key if llm_provider == "gemini" else None)
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

    modified_files_set = set(f.get("filename", "") for f in files if f.get("filename"))
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

        # Filter violations specifically to files modified in this PR
        pr_violations = []
        if modified_files_set:
            for v in review_results.violations:
                v_file = getattr(v, "file_path", "")
                if any(m_file in v_file or m_file in v.message for m_file in modified_files_set):
                    pr_violations.append(v)
        
        violations_messages = [v.message for v in pr_violations] if pr_violations else ["No static rule violations in modified PR files."]

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
        try:
            review_comment = await ai_client.generate_pr_review(
                diffs=diffs_str,
                violations=violations_messages,
                related_incidents=incidents_found,
                score=review_results.score,
                provider=llm_provider,
                api_key=api_key,
                model=ollama_model if llm_provider == "ollama" else None,
                ollama_url=ollama_url
            )
        except Exception as e:
            logger.error(f"AI Review generation failed or timed out: {e}")
            return {
                "status": "error",
                "message": f"AI Review generation timed out or failed: {str(e)}",
                "review_body": f"⚠️ **AI Review Generation Timed Out**: The local LLM ({llm_provider.upper()}) timed out processing this PR diff ({str(e)}).\n\n**Suggestions to fix:**\n1. Use a faster Ollama model (e.g. `qwen2.5:7b` or `qwen2.5-coder` instead of large models).\n2. Or switch to Cloud LLMs (**OpenAI** / **Gemini**) in **`⚙️ Settings`** for instant response times."
            }

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
            "review_body": review_comment,
            "score": review_results.score,
            "violations": violations_messages,
            "modified_files": list(modified_files_set),
            "owner": request.owner,
            "repo": request.repo,
            "pull_number": request.pull_number
        }

    finally:
        # 9. Clean up cloned codebase folder (Guaranteed execution)
        repo_cloner.cleanup_clone(clone_path)


@router.post("/scan-public", response_model=ArchitectureReviewResponse)
async def scan_public_repository(request: PublicScanRequest, raw_request: Request):
    """
    Scans any public or private Git repository (GitHub, GitLab, Bitbucket) by URL.
    Clones the repo using provided PATs if private, parses files, builds graph, runs Rule Engine, and returns the review.
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
        return {
            "owner": owner,
            "repo": repo,
            "score": review_results.score,
            "violations": review_results.violations
        }
    finally:
        # 5. Clean up temporary clone directory
        repo_cloner.cleanup_clone(clone_path)


@router.post("/fix-suggestion")
async def generate_ai_fix_suggestion(request: FixSuggestionRequest, raw_request: Request):
    """
    Calls AI (Ollama / OpenAI / Gemini) to generate step-by-step text-only refactoring suggestions.
    Does NOT output full code snippets or code blocks, only architectural guidance.
    """
    provider = request.provider or raw_request.headers.get("x-llm-provider")
    api_key = request.api_key or raw_request.headers.get("x-api-key")
    model = request.model or raw_request.headers.get("x-ollama-model")

    # Determine file language from extension
    ext = request.file_path.rsplit(".", 1)[-1].lower() if "." in request.file_path else "unknown"
    lang_map = {
        "py": "Python", "ts": "TypeScript", "tsx": "TypeScript/React",
        "js": "JavaScript", "jsx": "JavaScript/React", "dart": "Dart/Flutter",
        "java": "Java", "kt": "Kotlin", "swift": "Swift", "go": "Go",
        "rs": "Rust", "cs": "C#", "rb": "Ruby", "php": "PHP", "cpp": "C++", "c": "C",
    }
    lang = lang_map.get(ext, ext.upper())

    prompt = (
        f"You are an expert Principal Software Architect specializing in {lang} architectural best practices.\n"
        f"A static analysis rule engine detected a violation. Your job is to explain how to fix it.\n\n"
        f"VIOLATION DETAILS:\n"
        f"Rule: {request.rule_name}\n"
        f"Severity: {request.severity or 'HIGH'}\n"
        f"File: {request.file_path}\n"
        f"Language: {lang}\n"
        f"Issue: {request.message}\n"
        + (f"Hint: {request.suggested_fix}\n" if request.suggested_fix else "")
        + (f"Code Context:\n{request.code_snippet}\n" if request.code_snippet else "")
        + f"\n"
        f"Respond ONLY in the following plain-text format (no markdown, no asterisks, no hash symbols, no backticks):\n\n"
        f"[ROOT CAUSE]\n"
        f"Write 1-2 sentences explaining why this pattern is a problem and what it causes at runtime.\n\n"
        f"[IMPACT]\n"
        f"Write 1-2 sentences explaining the performance or correctness issue this causes.\n\n"
        f"[HOW TO FIX]\n"
        f"Write 3 to 5 numbered steps explaining exactly what the {lang} developer must do to fix this.\n\n"
        f"[BEST PRACTICE]\n"
        f"Write 1 sentence summarizing the architectural principle being enforced.\n\n"
        f"STRICT RULES:\n"
        f"- Do not use any markdown symbols: no **, no #, no -, no backticks.\n"
        f"- Use only plain English sentences and numbered lists.\n"
        f"- Each section must start exactly with its label in square brackets as shown above.\n"
        f"- Be specific to {lang}.\n"
    )

    try:
        fix_solution = await ai_client.generate_pr_review(
            diffs=prompt,
            violations=[request.message],
            related_incidents=[],
            score=80.0,
            provider=provider,
            api_key=api_key,
            model=model
        )
        return {"fix_suggestion": fix_solution}
    except Exception as e:
        logger.error(f"Failed to generate AI fix suggestion: {e}")
        return {
            "fix_suggestion": f"⚠️ **AI Suggestion Generation Timed Out / Failed**: {str(e)}\n\n**Architectural Guidance**: Extract database or repository calls outside loop blocks and perform bulk batch operations before iterating."
        }


# ==============================================================================
# Async Background Task Endpoints (Celery + Redis)
# ==============================================================================

from celery.result import AsyncResult
from app.worker.celery_app import celery_app
from app.worker.tasks import analyze_codebase_task, audit_pr_task

@router.post("/analyze-async")
async def analyze_codebase_async(request: ParseRepoRequest, raw_request: Request):
    """
    Triggers codebase analysis in the background using Celery.
    Returns the task ID immediately.
    """
    github_token = raw_request.headers.get("x-github-token")
    inst_id = None
    if not github_token:
        try:
            inst_id = await get_effective_installation_id(request.installation_id)
        except Exception:
            pass

    task = analyze_codebase_task.delay(
        owner=request.owner,
        repo=request.repo,
        installation_id=inst_id,
        github_token=github_token
    )
    return {"status": "accepted", "task_id": task.id}


@router.post("/scan-public-async")
async def scan_public_repository_async(request: PublicScanRequest, raw_request: Request):
    """
    Triggers public Git repository scan in the background.
    Returns the task ID immediately.
    """
    github_token = raw_request.headers.get("x-github-token")
    gitlab_token = raw_request.headers.get("x-gitlab-token")
    bitbucket_token = raw_request.headers.get("x-bitbucket-token")

    task = analyze_codebase_task.delay(
        repo_url=request.repo_url,
        github_token=github_token,
        gitlab_token=gitlab_token,
        bitbucket_token=bitbucket_token
    )
    return {"status": "accepted", "task_id": task.id}



@router.post("/pr-async")
async def analyze_and_review_pr_async(request: PRReviewRequest, raw_request: Request):
    """
    Triggers PR review audit in the background using Celery.
    Returns the task ID immediately.
    """
    llm_provider = raw_request.headers.get("x-llm-provider")
    openai_key = raw_request.headers.get("x-openai-key")
    gemini_key = raw_request.headers.get("x-gemini-key")
    ollama_model = raw_request.headers.get("x-ollama-model")
    ollama_url = raw_request.headers.get("x-ollama-url")
    
    api_key = openai_key if llm_provider == "openai" else (gemini_key if llm_provider == "gemini" else None)
    
    try:
        inst_id = await get_effective_installation_id(request.installation_id)
    except Exception:
        inst_id = None

    task = audit_pr_task.delay(
        owner=request.owner,
        repo=request.repo,
        pull_number=request.pull_number,
        installation_id=inst_id,
        github_token=raw_request.headers.get("x-github-token"),
        llm_provider=llm_provider,
        api_key=api_key,
        model=ollama_model,
        ollama_url=ollama_url
    )
    return {"status": "accepted", "task_id": task.id}


@router.get("/task-status/{task_id}")
async def get_task_status(task_id: str):
    """
    Retrieves the execution status and eventual result of a background Celery task.
    """
    res = AsyncResult(task_id, app=celery_app)
    
    response = {
        "task_id": task_id,
        "status": res.status, # PENDING, STARTED, RETRY, FAILURE, SUCCESS
    }
    
    if res.ready():
        if res.status == "SUCCESS":
            response["result"] = res.result
        else:
            response["error"] = str(res.result)
            
    return response

