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


from fastapi.responses import JSONResponse
import re
import random

# Confidence Tiers
LOW_CONFIDENCE_LANGS = {"c", "cpp", "rust", "swift", "php"}
MEDIUM_CONFIDENCE_LANGS = {"java", "go", "kotlin", "dart", "csharp"}

def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[-\s]+", "-", text)
    return text

def get_context_window(content: str, line_number: Optional[int], snippet: Optional[str]) -> str:
    lines = content.splitlines()
    total_lines = len(lines)
    
    # Determine target line (1-indexed)
    target_line = 1
    if line_number and 1 <= line_number <= total_lines:
        target_line = line_number
    elif snippet:
        # Find where the snippet matches in the file
        clean_snippet = snippet.strip().replace("\r\n", "\n")
        try:
            idx = content.replace("\r\n", "\n").find(clean_snippet)
            if idx != -1:
                target_line = content[:idx].count("\n") + 1
        except Exception:
            pass

    # Extract a contiguous window: 25 lines before and 25 lines after target_line
    start_idx = max(0, target_line - 26)
    end_idx = min(total_lines, target_line + 25)
    
    context_lines = lines[start_idx:end_idx]
    return "\n".join(context_lines)


def find_local_workspace_root(repo_name: Optional[str] = None) -> str:
    if repo_name:
        # Check standard folders for local repository clone
        search_dirs = [
            "/Users/aeologicbuddy/Desktop/Aeologic Projects",
            "/Users/aeologicbuddy/Desktop/Clients Project",
            "/Users/aeologicbuddy/Desktop"
        ]
        for sd in search_dirs:
            path = os.path.join(sd, repo_name)
            if os.path.exists(path):
                return os.path.abspath(path)

    # Start from current directory and go up until we find rules.md or backend/
    current = os.path.abspath(os.getcwd())
    for _ in range(4):
        if os.path.exists(os.path.join(current, "rules.md")) or os.path.exists(os.path.join(current, "backend")):
            return current
        current = os.path.dirname(current)
    return os.path.abspath(os.getcwd())


def apply_patch_to_content(content: str, original_snippet: str, fixed_snippet: str) -> str:
    # Normalize line endings
    content_norm = content.replace("\r\n", "\n")
    orig_norm = original_snippet.replace("\r\n", "\n")
    fixed_norm = fixed_snippet.replace("\r\n", "\n")
    
    if orig_norm in content_norm:
        return content_norm.replace(orig_norm, fixed_norm)
    
    # Fallback: if there are whitespace variations, try strip matching
    orig_strip = orig_norm.strip()
    if orig_strip in content_norm:
        return content_norm.replace(orig_strip, fixed_norm)
        
    raise ValueError("Could not find the original code snippet in the file to apply the fix.")


class ApplyFixRequest(BaseModel):
    file_path: str
    rule_name: str
    message: str
    severity: Optional[str] = "HIGH"
    suggested_fix: Optional[str] = None
    code_snippet: Optional[str] = None
    violation_line: Optional[int] = None
    owner: Optional[str] = None
    repo: Optional[str] = None
    pull_number: Optional[int] = None
    installation_id: Optional[int] = None
    provider: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None
    ollama_url: Optional[str] = None


class ApplyLocalFixRequest(BaseModel):
    file_path: str
    original_snippet: str
    fixed_code: str
    local_workspace_path: Optional[str] = None
    owner: Optional[str] = None
    repo: Optional[str] = None


class CreateFixPRRequest(BaseModel):
    file_path: str
    fixed_code: str
    rule_name: str
    message: str
    owner: str
    repo: str
    pull_number: Optional[int] = None
    installation_id: Optional[int] = None
    base_branch: Optional[str] = None
    provider: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None
    ollama_url: Optional[str] = None


@router.post("/preview-fix")
async def preview_fix_suggestion(request: ApplyFixRequest, raw_request: Request):
    """
    Validates language safety, fetches file contents (local workspace or GitHub fallback),
    detects if file has changed since scan, requests AI to generate a corrected block,
    and returns a structured side-by-side diff payload.
    """
    # 1. Language Safety check
    ext = request.file_path.rsplit(".", 1)[-1].lower() if "." in request.file_path else "unknown"
    if ext in LOW_CONFIDENCE_LANGS:
        return JSONResponse(
            status_code=400,
            content={
                "error": True,
                "code": "LOW_CONFIDENCE_LANGUAGE",
                "message": f"AI Auto-Fix is not reliable for the '{ext.upper()}' language.",
                "tip": "Please apply manual refactoring to address this violation."
            }
        )

    # 2. Get GitHub token/installation ID
    github_token = raw_request.headers.get("x-github-token")
    inst_id = None
    if not github_token:
        try:
            inst_id = await get_effective_installation_id(request.installation_id)
        except Exception:
            pass

    # 3. Resolve Branch/Ref if PR is provided
    ref = None
    if request.pull_number and request.owner and request.repo:
        try:
            pr_data = await github_client.get_pull_request(
                installation_id=inst_id,
                owner=request.owner,
                repo=request.repo,
                pull_number=request.pull_number,
                github_token=github_token
            )
            ref = pr_data.get("head", {}).get("ref")
        except Exception as e:
            logger.error(f"Failed to fetch PR info in preview-fix: {e}")

    # 4. Fetch Original Code Content
    original_content = None
    stale_warning = False
    
    # Try reading from local workspace first
    local_workspace_path = raw_request.headers.get("x-local-workspace-path")
    if not local_workspace_path:
        local_workspace_path = find_local_workspace_root(request.repo)
        
    local_file_path = os.path.join(local_workspace_path, request.file_path)
    if os.path.exists(local_file_path):
        try:
            with open(local_file_path, "r", encoding="utf-8", errors="ignore") as f:
                original_content = f.read()
            logger.info(f"Loaded original content locally from {local_file_path}")
            
            # Detect Stale File: check if code_snippet exists in current local file
            if request.code_snippet and request.code_snippet.strip():
                clean_snippet = request.code_snippet.strip().replace("\r\n", "\n")
                clean_content = original_content.replace("\r\n", "\n")
                if clean_snippet not in clean_content:
                    stale_warning = True
        except Exception as e:
            logger.warning(f"Could not read local file {local_file_path}: {e}")

    # Fallback to GitHub contents fetch
    if not original_content and request.owner and request.repo:
        try:
            file_data = await github_client.get_file_content(
                owner=request.owner,
                repo=request.repo,
                path=request.file_path,
                ref=ref,
                installation_id=inst_id,
                github_token=github_token
            )
            original_content = file_data.get("content", "")
            
            # Detect Stale File
            if request.code_snippet and request.code_snippet.strip():
                clean_snippet = request.code_snippet.strip().replace("\r\n", "\n")
                clean_content = original_content.replace("\r\n", "\n")
                if clean_snippet not in clean_content:
                    stale_warning = True
        except Exception as e:
            logger.warning(f"Could not fetch file content from GitHub: {e}")

    # Fallback to snippet from violation if both failed
    if not original_content:
        if request.code_snippet and request.code_snippet.strip():
            original_content = request.code_snippet
        else:
            return JSONResponse(
                status_code=400,
                content={
                    "error": True,
                    "code": "GITHUB_FETCH_FAILED",
                    "message": f"Could not retrieve file '{request.file_path}' content from disk/GitHub and no fallback code snippet was provided.",
                    "tip": "Verify your project path, branch settings, or file permissions."
                }
            )

    # 5. Extract smart context window
    code_context = get_context_window(original_content, request.violation_line, request.code_snippet)

    # 6. Call AI Client to generate fix
    provider = request.provider or raw_request.headers.get("x-llm-provider")
    api_key = request.api_key or raw_request.headers.get("x-api-key")
    model = request.model or raw_request.headers.get("x-ollama-model")
    ollama_url = request.ollama_url or raw_request.headers.get("x-ollama-url")

    # Map ext to friendly name
    lang_map = {
        "py": "Python", "ts": "TypeScript", "tsx": "TypeScript/React",
        "js": "JavaScript", "jsx": "JavaScript/React", "dart": "Dart/Flutter",
        "java": "Java", "kt": "Kotlin", "swift": "Swift", "go": "Go",
        "rs": "Rust", "cs": "C#", "rb": "Ruby", "php": "PHP", "cpp": "C++", "c": "C",
    }
    lang = lang_map.get(ext, ext.upper())

    try:
        fix_result = await ai_client.generate_code_fix(
            file_path=request.file_path,
            code_context=code_context,
            violation_message=request.message,
            rule_name=request.rule_name,
            severity=request.severity or "HIGH",
            suggested_fix=request.suggested_fix,
            language=lang,
            provider=provider,
            api_key=api_key,
            model=model,
            ollama_url=ollama_url
        )
        
        return {
            "original_snippet": code_context,
            "fixed_snippet": fix_result["fixed_code"],
            "explanation": fix_result["explanation"],
            "stale_warning": stale_warning,
            "language": ext
        }
    except Exception as e:
        logger.error(f"Failed to generate code fix: {e}")
        
        err_msg = str(e)
        code = "LLM_FAILED"
        tip = "Try switching your LLM provider to Gemini or OpenAI in Settings, or check if Ollama is running locally."
        
        if "rate limit" in err_msg.lower() or "429" in err_msg:
            code = "RATE_LIMITED"
            tip = "Rate limit reached. Wait 30 seconds and try again, or switch to a different LLM provider in Settings."
        elif "delimiters" in err_msg.lower() or "tag" in err_msg.lower():
            code = "NO_STRUCTURED_OUTPUT"
            tip = "The AI failed to return a cleanly delimited code patch. Click Preview again to retry."

        return JSONResponse(
            status_code=500,
            content={
                "error": True,
                "code": code,
                "message": f"AI Auto-Fix generation failed: {err_msg}",
                "tip": tip
            }
        )


@router.post("/apply-local-fix")
async def apply_local_fix(request: ApplyLocalFixRequest, raw_request: Request):
    """
    Applies the AI-generated code fix directly to the local workspace file on disk.
    Does not commit to git.
    """
    local_workspace_path = raw_request.headers.get("x-local-workspace-path")
    if not local_workspace_path:
        local_workspace_path = find_local_workspace_root(request.repo)
        
    local_file_path = os.path.abspath(os.path.join(local_workspace_path, request.file_path))
    
    # Security check: ensure path is within workspace
    if not local_file_path.startswith(os.path.abspath(local_workspace_path)):
        return JSONResponse(
            status_code=400,
            content={
                "error": True,
                "code": "INVALID_PATH",
                "message": "The resolved file path is outside the workspace directory.",
                "tip": "Ensure the file path is relative to the repository root."
            }
        )

    if not os.path.exists(local_file_path):
        return JSONResponse(
            status_code=404,
            content={
                "error": True,
                "code": "FILE_NOT_FOUND",
                "message": f"Could not find file on local disk: {request.file_path}",
                "tip": f"Expected location: {local_file_path}. Verify your workspace configuration."
            }
        )

    try:
        with open(local_file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
            
        updated_content = apply_patch_to_content(content, request.original_snippet, request.fixed_code)
        
        with open(local_file_path, "w", encoding="utf-8") as f:
            f.write(updated_content)
            
        return {
            "status": "success",
            "message": f"Successfully applied changes locally to '{request.file_path}' (unstaged).",
            "file_path": request.file_path,
            "absolute_path": local_file_path
        }
    except ValueError as ve:
        return JSONResponse(
            status_code=400,
            content={
                "error": True,
                "code": "PATCH_FAILED",
                "message": str(ve),
                "tip": "The original code may have been modified since the scan. Please refresh and try again."
            }
        )
    except Exception as e:
        logger.error(f"Failed to apply local fix: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "error": True,
                "code": "WRITE_FAILED",
                "message": f"Failed to write changes to local disk: {str(e)}",
                "tip": "Check if you have write permission for this file."
            }
        )


@router.post("/create-fix-pr")
async def create_fix_pr(request: CreateFixPRRequest, raw_request: Request):
    """
    Creates a new branch on GitHub, commits the fixed code snippet, and opens a Pull Request.
    """
    github_token = raw_request.headers.get("x-github-token")
    inst_id = None
    if not github_token:
        try:
            inst_id = await get_effective_installation_id(request.installation_id)
        except Exception:
            pass

    # 1. Resolve Target/Base Branch and base SHA
    base_branch = request.base_branch
    base_sha = None

    if request.pull_number:
        try:
            pr_data = await github_client.get_pull_request(
                installation_id=inst_id,
                owner=request.owner,
                repo=request.repo,
                pull_number=request.pull_number,
                github_token=github_token
            )
            # We want to branch off the head of the PR (nested PR)
            base_branch = pr_data.get("head", {}).get("ref")
            base_sha = pr_data.get("head", {}).get("sha")
        except Exception as e:
            return JSONResponse(
                status_code=400,
                content={
                    "error": True,
                    "code": "GITHUB_FETCH_FAILED",
                    "message": f"Failed to retrieve pull request info for PR #{request.pull_number}: {str(e)}",
                    "tip": "Check your network connection and token permissions."
                }
            )
    else:
        # Default target branch (main/master) if base_branch is not passed
        if not base_branch:
            base_branch = "main"
        
        # Get base branch latest commit SHA
        try:
            token = github_token or await github_client.get_installation_token(inst_id)
            headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "AI-Architecture-Code-Reviewer",
            }
            async with httpx.AsyncClient() as client:
                url = f"https://api.github.com/repos/{request.owner}/{request.repo}/git/ref/heads/{base_branch}"
                res = await client.get(url, headers=headers)
                if res.status_code == 200:
                    base_sha = res.json().get("object", {}).get("sha")
                else:
                    # Retry with master
                    if base_branch == "main":
                        url_alt = f"https://api.github.com/repos/{request.owner}/{request.repo}/git/ref/heads/master"
                        res_alt = await client.get(url_alt, headers=headers)
                        if res_alt.status_code == 200:
                            base_branch = "master"
                            base_sha = res_alt.json().get("object", {}).get("sha")
            
            if not base_sha:
                raise ValueError(f"Could not resolve branch '{base_branch}' SHA")
        except Exception as e:
            return JSONResponse(
                status_code=400,
                content={
                    "error": True,
                    "code": "GITHUB_FETCH_FAILED",
                    "message": f"Could not locate base branch '{base_branch}': {str(e)}",
                    "tip": "Verify the branch name exists on GitHub."
                }
            )

    # 2. Generate Safe Branch Name
    branch_slug = slugify(request.rule_name)[:30]
    rand_id = random.randint(1000, 9999)
    new_branch = f"ai-fix/{branch_slug}-{rand_id}"

    # 3. Create Branch
    try:
        await github_client.create_branch(
            owner=request.owner,
            repo=request.repo,
            new_branch=new_branch,
            base_sha=base_sha,
            installation_id=inst_id,
            github_token=github_token
        )
    except GitHubAPIError as gae:
        return JSONResponse(
            status_code=gae.status_code,
            content={
                "error": True,
                "code": "BRANCH_CREATION_FAILED",
                "message": f"Failed to create new branch '{new_branch}': {str(gae)}",
                "tip": "Check if target branch protection rules block branch creation by the app."
            }
        )

    # 4. Fetch target file's current SHA on the new branch to prepare for update
    file_sha = ""
    try:
        file_data = await github_client.get_file_content(
            owner=request.owner,
            repo=request.repo,
            path=request.file_path,
            ref=new_branch,
            installation_id=inst_id,
            github_token=github_token
        )
        file_sha = file_data.get("sha", "")
    except Exception as e:
        return JSONResponse(
            status_code=400,
            content={
                "error": True,
                "code": "GITHUB_FETCH_FAILED",
                "message": f"Failed to fetch original file hash from new branch '{new_branch}': {str(e)}",
                "tip": "Verify that file exists in the repo and path is correct."
            }
        )

    # 5. Commit change to new branch
    commit_msg = f"style(arch): auto-fix {request.rule_name} in {request.file_path.split('/')[-1]} [AI]"
    try:
        await github_client.commit_file_change(
            owner=request.owner,
            repo=request.repo,
            path=request.file_path,
            content=request.fixed_code,
            sha=file_sha,
            branch=new_branch,
            message=commit_msg,
            installation_id=inst_id,
            github_token=github_token
        )
    except GitHubAPIError as gae:
        return JSONResponse(
            status_code=gae.status_code,
            content={
                "error": True,
                "code": "COMMIT_FAILED",
                "message": f"Could not commit changes to branch '{new_branch}': {str(gae)}",
                "tip": "The file might have been modified concurrently. Try scanning again."
            }
        )

    # 6. Open Pull Request targeting base_branch
    pr_title = f"🤖 [AI Fix] Resolve {request.rule_name} in {request.file_path.split('/')[-1]}"
    pr_body = (
        f"### 🤖 Automated Architecture Fix\n\n"
        f"This Pull Request applies the suggested architectural refactoring to fix the following violation:\n"
        f"- **Violation**: {request.rule_name}\n"
        f"- **File**: `{request.file_path}`\n"
        f"- **Details**: {request.message}\n\n"
        f"Please review the diff and run tests before merging."
    )

    try:
        pr_data = await github_client.create_pull_request(
            owner=request.owner,
            repo=request.repo,
            title=pr_title,
            body=pr_body,
            head_branch=new_branch,
            base_branch=base_branch,
            installation_id=inst_id,
            github_token=github_token
        )
        return {
            "status": "success",
            "branch_name": new_branch,
            "pr_url": pr_data.get("html_url", ""),
            "pr_number": pr_data.get("number", 0)
        }
    except GitHubAPIError as gae:
        return JSONResponse(
            status_code=gae.status_code,
            content={
                "error": True,
                "code": "PR_CREATION_FAILED",
                "message": f"Branch was created and changes committed, but failed to open PR: {str(gae)}",
                "tip": f"You can open the Pull Request manually on GitHub from the branch '{new_branch}'."
            }
        )


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

