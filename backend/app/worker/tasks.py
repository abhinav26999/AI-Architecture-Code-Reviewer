import os
import asyncio
import logging
from typing import List, Dict, Any, Optional
from app.worker.celery_app import celery_app
from app.core.config import settings
from app.services.ingestion.cloner import repo_cloner
from app.services.parser.ast_parser import ast_parser
from app.services.dependency_graph.graph_builder import graph_builder
from app.services.rules.rule_engine import rule_engine
from app.services.github.github_client import github_client
from app.services.embeddings.rag_service import rag_service
from app.services.ai.ai_client import ai_client

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
    ".go", ".rs", ".java", ".cpp", ".c", ".h", ".cs", ".php", ".swift", ".kt", ".dart"
}

def run_async(coro):
    """Helper to run async functions inside synchronous Celery worker threads."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

@celery_app.task(bind=True, name="app.worker.tasks.analyze_codebase_task")
def analyze_codebase_task(
    self,
    owner: Optional[str] = None,
    repo: Optional[str] = None,
    installation_id: Optional[int] = None,
    github_token: Optional[str] = None,
    repo_url: Optional[str] = None,
    gitlab_token: Optional[str] = None,
    bitbucket_token: Optional[str] = None
) -> Dict[str, Any]:
    """
    Celery task to run a complete architectural review of a repository in the background.
    Supports either app integration (owner/repo) or public/arbitrary Git repo URL.
    """
    logger.info(f"Celery: Starting scan (Task ID: {self.request.id})")
    
    # 1. Clone repository
    try:
        if repo_url:
            logger.info(f"Celery: Cloning public/external repository URL: {repo_url}")
            clone_path, resolved_owner, resolved_repo = run_async(repo_cloner.clone_public_repository(
                repo_url=repo_url,
                github_token=github_token,
                gitlab_token=gitlab_token,
                bitbucket_token=bitbucket_token
            ))
            owner = resolved_owner
            repo = resolved_repo
        elif owner and repo:
            logger.info(f"Celery: Cloning app integrated repository: {owner}/{repo}")
            clone_path = run_async(repo_cloner.clone_repository(
                owner=owner,
                repo=repo,
                installation_id=installation_id,
                github_token=github_token
            ))
        else:
            return {"status": "error", "error": "Missing repository parameters (either owner/repo or repo_url must be provided)"}
    except Exception as e:
        logger.error(f"Celery: Repository cloning failed: {e}")
        return {"status": "error", "error": f"Repository cloning failed: {str(e)}"}

    parsed_files = []
    ignored_dirs = {".git", "node_modules", "venv", ".venv", "__pycache__", "dist", "build"}

    try:
        # 2. Extract AST Metadata
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
                        logger.error(f"Error parsing file {rel_path} in Celery task: {e}")
                        continue

        # 3. Build Graph
        graph = graph_builder.build_graph(
            owner=owner,
            repo=repo,
            parsed_files=parsed_files
        )

        # 4. Run Rule Engine Checks
        review_results = run_async(rule_engine.run_review(
            owner=owner,
            repo=repo,
            parsed_files=parsed_files,
            graph=graph,
            clone_path=clone_path
        ))
        
        # Serialize the response schema to plain dict for Celery JSON serialization
        return {
            "status": "success",
            "owner": owner,
            "repo": repo,
            "score": review_results.score,
            "violations": [
                {
                    "rule_name": v.rule_name,
                    "severity": v.severity,
                    "file_path": v.file_path,
                    "line": v.line,
                    "message": v.message,
                    "suggested_fix": v.suggested_fix,
                    "code_snippet": v.code_snippet
                } for v in review_results.violations
            ],
            "graph": {
                "total_files": graph.total_files,
                "nodes": [
                    {
                        "file_path": n.file_path,
                        "metrics": {
                            "instability": n.metrics.instability,
                            "afferent_coupling": n.metrics.afferent_coupling,
                            "efferent_coupling": n.metrics.efferent_coupling
                        }
                    } for n in graph.nodes
                ],
                "edges": [{"source": e.source, "target": e.target} for e in graph.edges],
                "circular_dependencies": graph.circular_dependencies,
                "average_instability": graph.average_instability
            }
        }

    except Exception as e:
        logger.exception(f"Unexpected failure in analyze_codebase_task: {e}")
        return {"status": "error", "error": f"Execution failed: {str(e)}"}
    finally:
        # 5. Clean up cloned codebase folder (Guaranteed execution)
        repo_cloner.cleanup_clone(clone_path)


@celery_app.task(bind=True, name="app.worker.tasks.audit_pr_task")
def audit_pr_task(
    self,
    owner: str,
    repo: str,
    pull_number: int,
    installation_id: Optional[int] = None,
    github_token: Optional[str] = None,
    llm_provider: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    ollama_url: Optional[str] = None
) -> Dict[str, Any]:
    """
    Celery task to run a complete PR audit (diff, rule review, pgvector lookup, LLM call) in the background.
    """
    logger.info(f"Celery: Starting PR review for {owner}/{repo} #{pull_number} (Task ID: {self.request.id})")
    
    # 1. Fetch changed files and diff patches from GitHub
    try:
        files = run_async(github_client.get_pull_request_files(
            installation_id=installation_id,
            owner=owner,
            repo=repo,
            pull_number=pull_number
        ))
    except Exception as e:
        logger.error(f"Celery: Failed to fetch PR files: {e}")
        return {"status": "error", "error": f"Failed to fetch PR files: {str(e)}"}

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
        clone_path = run_async(repo_cloner.clone_repository(
            owner=owner,
            repo=repo,
            installation_id=installation_id,
            github_token=github_token
        ))
    except Exception as e:
        logger.error(f"Celery: Repository cloning failed: {e}")
        return {"status": "error", "error": f"Repository cloning failed: {str(e)}"}

    parsed_files = []
    ignored_dirs = {".git", "node_modules", "venv", ".venv", "__pycache__", "dist", "build"}

    try:
        # 3. Extract AST Metadata
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
                        logger.error(f"Error parsing file {rel_path} in Celery PR task: {e}")
                        continue

        # 4. Build Graph
        graph = graph_builder.build_graph(
            owner=owner,
            repo=repo,
            parsed_files=parsed_files
        )

        # 5. Run Rule Engine Checks
        review_results = run_async(rule_engine.run_review(
            owner=owner,
            repo=repo,
            parsed_files=parsed_files,
            graph=graph,
            clone_path=clone_path
        ))

        # Filter violations to only modified files in the PR
        pr_violations = [v for v in review_results.violations if v.file_path in modified_files_set]

        # 6. Retrieve Outage Incident Context (RAG Vector Search)
        related_incidents = []
        if pr_violations:
            try:
                # Query RAG asynchronously
                search_queries = [v.message for v in pr_violations]
                for query in search_queries[:3]:  # Cap at 3 queries for performance
                    matches = run_async(rag_service.search_outages(query, limit=1))
                    for match in matches:
                        incident = match.get("incident_summary", "")
                        if incident:
                            related_incidents.append(incident)
            except Exception as re_err:
                logger.error(f"Celery: RAG Incident search failed: {re_err}")

        # 7. Invoke LLM for Critique Generation
        try:
            review_body = run_async(ai_client.generate_pr_review(
                diffs=diffs_str,
                violations=[v.message for v in pr_violations],
                related_incidents=related_incidents,
                score=review_results.score,
                provider=llm_provider,
                api_key=api_key,
                model=model,
                ollama_url=ollama_url
            ))
        except Exception as llm_err:
            logger.error(f"Celery: LLM PR Critique failed: {llm_err}")
            review_body = f"⚠️ **AI Review Generation Failed**: {str(llm_err)}"

        # 8. Post review comment to GitHub PR
        try:
            run_async(github_client.post_pull_request_comment(
                installation_id=installation_id,
                owner=owner,
                repo=repo,
                pull_number=pull_number,
                comment_body=review_body
            ))
            comment_posted = True
        except Exception as gh_err:
            logger.error(f"Celery: Failed to post comment on GitHub: {gh_err}")
            comment_posted = False

        return {
            "status": "success",
            "review_body": review_body,
            "score": review_results.score,
            "comment_posted": comment_posted,
            "modified_files": list(modified_files_set),
            "violations": [
                {
                    "rule_name": v.rule_name,
                    "severity": v.severity,
                    "file_path": v.file_path,
                    "line": v.line,
                    "message": v.message
                } for v in pr_violations
            ]
        }

    except Exception as e:
        logger.exception(f"Unexpected failure in audit_pr_task: {e}")
        return {"status": "error", "error": f"Execution failed: {str(e)}"}
    finally:
        # 9. Cleanup
        repo_cloner.cleanup_clone(clone_path)
