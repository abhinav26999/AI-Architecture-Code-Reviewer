import time
import logging
from typing import Dict, Any, List, Optional
import httpx
import jwt
from app.core.config import settings

logger = logging.getLogger(__name__)


class GitHubAPIError(Exception):
    """Exception raised for errors during GitHub API interactions."""
    def __init__(self, message: str, status_code: int = 500, response_body: Optional[str] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class GitHubClient:
    def __init__(self):
        # Cache for installation tokens: {installation_id: {"token": str, "expires_at": float}}
        self._token_cache: Dict[int, Dict[str, Any]] = {}
        self.base_url = "https://api.github.com"

    def _generate_jwt(self) -> str:
        """Generates a JWT signed with the App's private key for App-level authentication."""
        app_id = settings.GITHUB_APP_ID
        private_key = settings.private_key_content

        if not app_id or not private_key:
            raise GitHubAPIError(
                "GitHub App ID or Private Key is not configured.",
                status_code=500
            )

        now = int(time.time())
        payload = {
            "iat": now - 60,  # Allow for small clock drift
            "exp": now + (10 * 60),  # Max lifespan 10 minutes
            "iss": str(app_id),
        }

        try:
            return jwt.encode(payload, private_key, algorithm="RS256")
        except Exception as e:
            logger.error(f"Failed to encode JWT: {e}")
            raise GitHubAPIError(
                f"Failed to generate JWT: {str(e)}",
                status_code=500
            )

    async def get_installation_token(self, installation_id: int) -> str:
        """Retrieves a cached token or requests a new installation access token from GitHub."""
        now = time.time()
        
        # Check cache (renew token 2 minutes before expiry to be safe)
        if installation_id in self._token_cache:
            cache = self._token_cache[installation_id]
            if cache["expires_at"] - now > 120:
                return cache["token"]

        jwt_token = self._generate_jwt()
        headers = {
            "Authorization": f"Bearer {jwt_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "AI-Architecture-Code-Reviewer",
        }

        async with httpx.AsyncClient() as client:
            url = f"{self.base_url}/app/installations/{installation_id}/access_tokens"
            try:
                response = await client.post(url, headers=headers)
                if response.status_code != 201:
                    logger.error(f"Failed to get token for installation {installation_id}: {response.text}")
                    raise GitHubAPIError(
                        f"Failed to get installation token: {response.text}",
                        status_code=response.status_code,
                        response_body=response.text
                    )
                
                data = response.json()
                token = data["token"]
                
                # Parse expiration (GitHub uses ISO 8601 string, e.g., '2016-07-11T19:14:56Z')
                # For simplicity, parse and convert or use standard expiration (usually 1 hour)
                expires_at_str = data.get("expires_at")
                if expires_at_str:
                    # Strip Z and parse
                    clean_date = expires_at_str.replace("Z", "")
                    # Workaround for Python's ISO parsing if timezone is missing
                    if "+" not in clean_date:
                        clean_date += "+00:00"
                    from datetime import datetime
                    expires_at = datetime.fromisoformat(clean_date).timestamp()
                else:
                    expires_at = now + 3600

                self._token_cache[installation_id] = {
                    "token": token,
                    "expires_at": expires_at
                }
                return token
            except httpx.HTTPError as e:
                logger.error(f"HTTP connection error when requesting installation token: {e}")
                raise GitHubAPIError(f"Connection error to GitHub: {str(e)}", status_code=500)

    async def get_app_installations(self) -> List[Dict[str, Any]]:
        """Lists all installations of the GitHub App."""
        jwt_token = self._generate_jwt()
        headers = {
            "Authorization": f"Bearer {jwt_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "AI-Architecture-Code-Reviewer",
        }

        async with httpx.AsyncClient() as client:
            url = f"{self.base_url}/app/installations"
            try:
                response = await client.get(url, headers=headers)
                if response.status_code != 200:
                    raise GitHubAPIError(
                        f"Failed to list installations: {response.text}",
                        status_code=response.status_code,
                        response_body=response.text
                    )
                return response.json()
            except httpx.HTTPError as e:
                raise GitHubAPIError(f"Connection error to GitHub: {str(e)}")

    async def get_repositories(self, installation_id: int) -> List[Dict[str, Any]]:
        """Lists repositories accessible to a specific installation."""
        token = await self.get_installation_token(installation_id)
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "AI-Architecture-Code-Reviewer",
        }

        async with httpx.AsyncClient() as client:
            url = f"{self.base_url}/installation/repositories"
            try:
                response = await client.get(url, headers=headers)
                if response.status_code != 200:
                    raise GitHubAPIError(
                        f"Failed to list repositories: {response.text}",
                        status_code=response.status_code,
                        response_body=response.text
                    )
                return response.json().get("repositories", [])
            except httpx.HTTPError as e:
                raise GitHubAPIError(f"Connection error to GitHub: {str(e)}")

    async def get_pull_request(self, installation_id: Optional[int], owner: str, repo: str, pull_number: int, github_token: Optional[str] = None) -> Dict[str, Any]:
        """Fetches detailed information for a single pull request."""
        if github_token and github_token.strip():
            token = github_token.strip()
        else:
            token = await self.get_installation_token(installation_id)

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "AI-Architecture-Code-Reviewer",
        }

        async with httpx.AsyncClient() as client:
            url = f"{self.base_url}/repos/{owner}/{repo}/pulls/{pull_number}"
            try:
                response = await client.get(url, headers=headers)
                if response.status_code != 200:
                    raise GitHubAPIError(
                        f"Failed to get pull request #{pull_number} from {owner}/{repo}: {response.text}",
                        status_code=response.status_code,
                        response_body=response.text
                    )
                return response.json()
            except httpx.HTTPError as e:
                raise GitHubAPIError(f"Connection error to GitHub: {str(e)}")

    async def list_pull_requests(self, installation_id: Optional[int], owner: str, repo: str, github_token: Optional[str] = None) -> List[Dict[str, Any]]:
        """Lists open pull requests for a specific repository."""
        if github_token and github_token.strip():
            token = github_token.strip()
        else:
            token = await self.get_installation_token(installation_id)

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "AI-Architecture-Code-Reviewer",
        }

        async with httpx.AsyncClient() as client:
            url = f"{self.base_url}/repos/{owner}/{repo}/pulls?state=all&sort=updated&direction=desc&per_page=30"
            try:
                response = await client.get(url, headers=headers)
                if response.status_code != 200:
                    raise GitHubAPIError(
                        f"Failed to list pull requests for {owner}/{repo}: {response.text}",
                        status_code=response.status_code,
                        response_body=response.text
                    )
                return response.json()
            except httpx.HTTPError as e:
                raise GitHubAPIError(f"Connection error to GitHub: {str(e)}")

    async def get_pull_request_files(self, installation_id: Optional[int], owner: str, repo: str, pull_number: int, github_token: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetches the list of files modified in a pull request, including diff patches."""
        if github_token and github_token.strip():
            token = github_token.strip()
        else:
            token = await self.get_installation_token(installation_id)

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "AI-Architecture-Code-Reviewer",
        }

        async with httpx.AsyncClient() as client:
            url = f"{self.base_url}/repos/{owner}/{repo}/pulls/{pull_number}/files"
            try:
                response = await client.get(url, headers=headers)
                if response.status_code != 200:
                    raise GitHubAPIError(
                        f"Failed to get files for PR #{pull_number}: {response.text}",
                        status_code=response.status_code,
                        response_body=response.text
                    )
                return response.json()
            except httpx.HTTPError as e:
                raise GitHubAPIError(f"Connection error to GitHub: {str(e)}")

    async def create_pull_request_review(
        self,
        installation_id: int,
        owner: str,
        repo: str,
        pull_number: int,
        body: str,
        event: str = "COMMENT"
    ) -> Dict[str, Any]:
        """Creates a Pull Request review containing the AI review comments."""
        token = await self.get_installation_token(installation_id)
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "AI-Architecture-Code-Reviewer",
        }
        payload = {
            "body": body,
            "event": event
        }

        async with httpx.AsyncClient() as client:
            url = f"{self.base_url}/repos/{owner}/{repo}/pulls/{pull_number}/reviews"
            try:
                response = await client.post(url, headers=headers, json=payload)
                if response.status_code not in (200, 201):
                    raise GitHubAPIError(
                        f"Failed to post PR review comment: {response.text}",
                        status_code=response.status_code,
                        response_body=response.text
                    )
                return response.json()
            except httpx.HTTPError as e:
                raise GitHubAPIError(f"Connection error to GitHub: {str(e)}")

    async def get_file_content(
        self,
        owner: str,
        repo: str,
        path: str,
        ref: Optional[str] = None,
        installation_id: Optional[int] = None,
        github_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """Reads original code content and file SHA from GitHub Contents API."""
        if github_token and github_token.strip():
            token = github_token.strip()
        else:
            token = await self.get_installation_token(installation_id)

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "AI-Architecture-Code-Reviewer",
        }

        url = f"{self.base_url}/repos/{owner}/{repo}/contents/{path}"
        params = {}
        if ref:
            params["ref"] = ref

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(url, headers=headers, params=params)
                if response.status_code == 401:
                    raise GitHubAPIError("GitHub token is invalid or expired.", status_code=401)
                elif response.status_code == 403:
                    raise GitHubAPIError("Access denied: token lacks read access to this repo.", status_code=403)
                elif response.status_code == 404:
                    raise GitHubAPIError("File not found — it may have been deleted or renamed on this branch.", status_code=404)
                elif response.status_code == 429:
                    raise GitHubAPIError("GitHub API rate limit reached. Wait a few minutes and try again.", status_code=429)
                elif response.status_code not in (200, 201):
                    raise GitHubAPIError(f"Failed to fetch file content: {response.text}", status_code=response.status_code)
                
                data = response.json()
                import base64
                encoded_content = data.get("content", "")
                # GitHub returns base64 content with newlines, strip them
                decoded_content = base64.b64decode(encoded_content.replace("\n", "")).decode("utf-8", errors="ignore")
                
                return {
                    "content": decoded_content,
                    "sha": data.get("sha", "")
                }
            except httpx.HTTPError as e:
                raise GitHubAPIError(f"Connection error to GitHub: {str(e)}")

    async def create_branch(
        self,
        owner: str,
        repo: str,
        new_branch: str,
        base_sha: str,
        installation_id: Optional[int] = None,
        github_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """Creates a new branch (Git ref) pointing to a base branch SHA."""
        if github_token and github_token.strip():
            token = github_token.strip()
        else:
            token = await self.get_installation_token(installation_id)

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "AI-Architecture-Code-Reviewer",
        }

        url = f"{self.base_url}/repos/{owner}/{repo}/git/refs"
        payload = {
            "ref": f"refs/heads/{new_branch}",
            "sha": base_sha
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(url, headers=headers, json=payload)
                if response.status_code == 422:
                    raise GitHubAPIError(f"Branch '{new_branch}' already exists or ref is invalid.", status_code=422)
                elif response.status_code not in (200, 201):
                    raise GitHubAPIError(f"Failed to create branch: {response.text}", status_code=response.status_code)
                return response.json()
            except httpx.HTTPError as e:
                raise GitHubAPIError(f"Connection error to GitHub: {str(e)}")

    async def commit_file_change(
        self,
        owner: str,
        repo: str,
        path: str,
        content: str,
        sha: str,
        branch: str,
        message: str,
        installation_id: Optional[int] = None,
        github_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """Commits updated content directly to a specific branch via GitHub Contents API."""
        if github_token and github_token.strip():
            token = github_token.strip()
        else:
            token = await self.get_installation_token(installation_id)

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "AI-Architecture-Code-Reviewer",
        }

        import base64
        encoded_content = base64.b64encode(content.encode("utf-8")).decode("utf-8")
        
        url = f"{self.base_url}/repos/{owner}/{repo}/contents/{path}"
        payload = {
            "message": message,
            "content": encoded_content,
            "sha": sha,
            "branch": branch
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.put(url, headers=headers, json=payload)
                if response.status_code == 409:
                    raise GitHubAPIError("Conflict: The file has changed since the scan. Please refresh and try again.", status_code=409)
                elif response.status_code not in (200, 201):
                    raise GitHubAPIError(f"Failed to commit file change: {response.text}", status_code=response.status_code)
                return response.json()
            except httpx.HTTPError as e:
                raise GitHubAPIError(f"Connection error to GitHub: {str(e)}")

    async def create_pull_request(
        self,
        owner: str,
        repo: str,
        title: str,
        body: str,
        head_branch: str,
        base_branch: str,
        installation_id: Optional[int] = None,
        github_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """Creates a Pull Request targeting a base branch."""
        if github_token and github_token.strip():
            token = github_token.strip()
        else:
            token = await self.get_installation_token(installation_id)

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "AI-Architecture-Code-Reviewer",
        }

        url = f"{self.base_url}/repos/{owner}/{repo}/pulls"
        payload = {
            "title": title,
            "body": body,
            "head": head_branch,
            "base": base_branch
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(url, headers=headers, json=payload)
                if response.status_code not in (200, 201):
                    raise GitHubAPIError(f"Failed to create Pull Request: {response.text}", status_code=response.status_code)
                return response.json()
            except httpx.HTTPError as e:
                raise GitHubAPIError(f"Connection error to GitHub: {str(e)}")


# Singleton instance
github_client = GitHubClient()
