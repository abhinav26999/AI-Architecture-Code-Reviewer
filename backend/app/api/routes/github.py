from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, Request
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


@router.get("/public-pulls")
async def list_public_pull_requests(
    raw_request: Request,
    repo_url: str = Query(..., description="Repository URL (e.g. https://github.com/owner/repo)")
):
    """Fetches list of pull requests / merge requests for GitHub, Bitbucket, or GitLab URLs."""
    import re
    import httpx
    import urllib.parse

    clean_url = repo_url.strip()
    match = re.match(r"https?://(?:[^/@]+@)?(?:www\.)?(github\.com|bitbucket\.org|gitlab\.com)/([^/]+)/([^/]+?)(?:\.git|/.*)?$", clean_url)
    if not match:
        return []

    host = match.group(1).lower()
    owner = match.group(2)
    repo = match.group(3)

    gh_token = raw_request.headers.get("x-github-token")
    bb_token = raw_request.headers.get("x-bitbucket-token")
    gl_token = raw_request.headers.get("x-gitlab-token")

    async with httpx.AsyncClient() as client:
        try:
            if host == "github.com":
                api_url = f"https://api.github.com/repos/{owner}/{repo}/pulls?state=all&sort=updated&direction=desc&per_page=30"
                headers = {"Accept": "application/vnd.github+json", "User-Agent": "AI-Architecture-Code-Reviewer"}
                if gh_token and gh_token.strip():
                    headers["Authorization"] = f"Bearer {gh_token.strip()}"
                
                res = await client.get(api_url, headers=headers, timeout=6.0)
                if res.status_code == 200:
                    return res.json()

            elif host == "bitbucket.org":
                api_url = f"https://api.bitbucket.org/2.0/repositories/{owner}/{repo}/pullrequests?pagelen=30"
                headers = {"User-Agent": "AI-Architecture-Code-Reviewer"}
                if bb_token and bb_token.strip():
                    if ":" in bb_token:
                        u, p = bb_token.strip().split(":", 1)
                        headers["Authorization"] = httpx.BasicAuth(u.strip(), p.strip())._auth_header
                    else:
                        headers["Authorization"] = f"Bearer {bb_token.strip()}"

                res = await client.get(api_url, headers=headers, timeout=6.0)
                if res.status_code == 200:
                    data = res.json()
                    formatted_prs = []
                    for item in data.get("values", []):
                        formatted_prs.append({
                            "id": item.get("id"),
                            "number": item.get("id"),
                            "title": item.get("title", ""),
                            "state": item.get("state", "open").lower(),
                            "user": {"login": item.get("author", {}).get("display_name", "Author")},
                            "head": {"ref": item.get("source", {}).get("branch", {}).get("name", "")},
                            "base": {"ref": item.get("destination", {}).get("branch", {}).get("name", "")}
                        })
                    return formatted_prs

            elif host == "gitlab.com":
                project_path = urllib.parse.quote(f"{owner}/{repo}", safe="")
                api_url = f"https://gitlab.com/api/v4/projects/{project_path}/merge_requests?per_page=30"
                headers = {"User-Agent": "AI-Architecture-Code-Reviewer"}
                if gl_token and gl_token.strip():
                    headers["PRIVATE-TOKEN"] = gl_token.strip()

                res = await client.get(api_url, headers=headers, timeout=6.0)
                if res.status_code == 200:
                    data = res.json()
                    formatted_prs = []
                    for item in data:
                        formatted_prs.append({
                            "id": item.get("id"),
                            "number": item.get("iid"),
                            "title": item.get("title", ""),
                            "state": item.get("state", "opened"),
                            "user": {"login": item.get("author", {}).get("username", "Author")},
                            "head": {"ref": item.get("source_branch", "")},
                            "base": {"ref": item.get("target_branch", "")}
                        })
                    return formatted_prs

        except Exception as e:
            logger.error(f"Error fetching public pull requests for {repo_url}: {e}")
            return []

    return []


@router.get("/repos/{owner}/{repo}/pulls")
async def list_open_pull_requests(
    owner: str,
    repo: str,
    installation_id: Optional[int] = Query(None, description="GitHub App Installation ID")
):
    """Lists pull requests for a repository."""
    try:
        inst_id = await get_effective_installation_id(installation_id)
        pulls = await github_client.list_pull_requests(inst_id, owner, repo)
        return pulls
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
