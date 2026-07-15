from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
from app.services.github.github_client import github_client, GitHubAPIError
from app.schemas.github import (
    GitHubAppTestResponse,
    GitHubRepository,
    GitHubPullRequest,
    GitHubFileChange
)

router = APIRouter()


async def get_effective_installation_id(installation_id: Optional[int] = None) -> int:
    """Helper to get the provided installation ID or fallback to the first active installation."""
    if installation_id is not None:
        return installation_id

    try:
        installations = await github_client.get_app_installations()
        if not installations:
            raise HTTPException(
                status_code=404,
                detail="No installations found. Please install the GitHub App on a repository."
            )
        return installations[0]["id"]
    except GitHubAPIError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=f"Failed to fetch installations to find default: {str(e)}"
        )


@router.get("/test-auth", response_model=GitHubAppTestResponse)
async def test_auth():
    """
    Test App authentication by generating a JWT and calling the GitHub App Installations endpoint.
    This verifies that GITHUB_APP_ID and GITHUB_PRIVATE_KEY are correct.
    """
    try:
        installations = await github_client.get_app_installations()
        return GitHubAppTestResponse(
            status="success",
            app_id=str(github_client._generate_jwt() is not None),  # confirms generation worked
            client_id="Not verified (App ID works)",
            authenticated=True,
            message="Successfully authenticated as GitHub App!",
            details={"installations_count": len(installations), "installations": installations}
        )
    except GitHubAPIError as e:
        return GitHubAppTestResponse(
            status="error",
            app_id="",
            client_id="",
            authenticated=False,
            message=f"Authentication failed: {str(e)}",
            details={"status_code": e.status_code, "response_body": e.response_body}
        )
    except Exception as e:
        return GitHubAppTestResponse(
            status="error",
            app_id="",
            client_id="",
            authenticated=False,
            message=f"System error: {str(e)}",
            details=None
        )


@router.get("/installations")
async def list_installations():
    """Lists all installations of this GitHub App."""
    try:
        return await github_client.get_app_installations()
    except GitHubAPIError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))


@router.get("/repositories")
async def list_repositories(installation_id: Optional[int] = Query(None, description="GitHub App Installation ID")):
    """Lists repositories accessible to the GitHub App installation."""
    try:
        inst_id = await get_effective_installation_id(installation_id)
        repos = await github_client.get_repositories(inst_id)
        return repos
    except GitHubAPIError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))


@router.get("/repos/{owner}/{repo}/pulls/{pull_number}", response_model=GitHubPullRequest)
async def get_pull_request(
    owner: str,
    repo: str,
    pull_number: int,
    installation_id: Optional[int] = Query(None, description="GitHub App Installation ID")
):
    """Fetches details for a specific pull request."""
    try:
        inst_id = await get_effective_installation_id(installation_id)
        pr_data = await github_client.get_pull_request(inst_id, owner, repo, pull_number)
        return pr_data
    except GitHubAPIError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))


@router.get("/repos/{owner}/{repo}/pulls/{pull_number}/files", response_model=List[GitHubFileChange])
async def get_pull_request_files(
    owner: str,
    repo: str,
    pull_number: int,
    installation_id: Optional[int] = Query(None, description="GitHub App Installation ID")
):
    """Fetches list of files and their diff patches modified in a pull request."""
    try:
        inst_id = await get_effective_installation_id(installation_id)
        files = await github_client.get_pull_request_files(inst_id, owner, repo, pull_number)
        return files
    except GitHubAPIError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))
