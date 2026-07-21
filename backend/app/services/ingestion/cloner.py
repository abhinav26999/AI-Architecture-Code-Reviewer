import os
import shutil
import uuid
import logging
import asyncio
from app.core.config import settings
from app.services.github.github_client import github_client, GitHubAPIError

logger = logging.getLogger(__name__)


class ClonerError(Exception):
    """Exception raised for cloner failures."""
    pass


class RepositoryCloner:
    def __init__(self):
        self.base_dir = settings.resolved_temp_clone_dir

    async def clone_repository(
        self,
        owner: str,
        repo: str,
        installation_id: Optional[int] = None,
        github_token: Optional[str] = None
    ) -> str:
        """
        Shallow clones a GitHub repository using either a user-provided PAT (github_token)
        or a GitHub App installation access token.
        Clones into a unique directory within backend/temp_clones/ and returns the path.
        """
        # Ensure base clones directory exists
        os.makedirs(self.base_dir, exist_ok=True)

        token = None
        if github_token and github_token.strip():
            token = github_token.strip()
        elif installation_id is not None:
            try:
                token = await github_client.get_installation_token(installation_id)
            except GitHubAPIError as e:
                logger.error(f"Failed to get installation token for cloning: {e}")
                raise ClonerError(f"Authentication failure: {str(e)}")

        # Create unique subdirectory name
        unique_id = uuid.uuid4().hex[:10]
        clone_dirname = f"{owner}_{repo}_{unique_id}"
        clone_path = os.path.join(self.base_dir, clone_dirname)
        
        # Security sanity check: resolve path
        clone_path = os.path.abspath(clone_path)
        if not clone_path.startswith(os.path.abspath(self.base_dir)):
            raise ClonerError("Invalid clone target path generated.")

        # Construct authentication clone URL
        if token:
            clone_url = f"https://x-access-token:{token}@github.com/{owner}/{repo}.git"
        else:
            clone_url = f"https://github.com/{owner}/{repo}.git"

        logger.info(f"Cloning {owner}/{repo} (depth=1) into {clone_path}...")
        
        # Async subprocess clone command
        cmd = [
            "git", "clone", "--depth", "1",
            clone_url,
            clone_path
        ]
        
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                err_msg = stderr.decode().strip()
                # Clean up any potential token leaks in log messages
                cleaned_err = err_msg.replace(token, "******")
                logger.error(f"Git clone failed: {cleaned_err}")
                
                # Delete target path if git created partial directory
                self.cleanup_clone(clone_path)
                raise ClonerError(f"Git clone failed: {cleaned_err}")
                
            logger.info(f"Successfully cloned {owner}/{repo} to {clone_path}")
            return clone_path
            
        except Exception as e:
            if not isinstance(e, ClonerError):
                logger.exception("Unexpected error during git clone")
                self.cleanup_clone(clone_path)
                raise ClonerError(f"Unexpected cloner error: {str(e)}")
            raise

    async def clone_public_repository(
        self,
        repo_url: str,
        github_token: Optional[str] = None,
        gitlab_token: Optional[str] = None,
        bitbucket_token: Optional[str] = None
    ) -> tuple:
        """
        Shallow clones a public or private repository from GitHub, GitLab, or Bitbucket.
        Uses authentication tokens if provided for private repositories.
        Returns a tuple of (clone_path, owner, repo).
        """
        import re

        # Validate and extract owner/repo from GitHub, Bitbucket, or GitLab URL
        match = re.match(r"https?://(?:www\.)?(github\.com|bitbucket\.org|gitlab\.com)/([^/]+)/([^/]+?)(?:\.git)?/?$", repo_url.strip())
        if not match:
            raise ClonerError(
                f"Invalid Git URL format: '{repo_url}'. "
                "Expected URL from GitHub, Bitbucket, or GitLab (e.g. https://bitbucket.org/workspace/repo)"
            )

        host = match.group(1).lower()
        owner = match.group(2)
        repo = match.group(3)

        os.makedirs(self.base_dir, exist_ok=True)

        unique_id = uuid.uuid4().hex[:10]
        clone_dirname = f"{owner}_{repo}_{unique_id}"
        clone_path = os.path.join(self.base_dir, clone_dirname)
        clone_path = os.path.abspath(clone_path)

        if not clone_path.startswith(os.path.abspath(self.base_dir)):
            raise ClonerError("Invalid clone target path generated.")

        # Construct authenticated clone URL depending on host & available token
        active_token = None
        if host == "github.com" and github_token and github_token.strip():
            active_token = github_token.strip()
            clone_url = f"https://x-access-token:{active_token}@github.com/{owner}/{repo}.git"
        elif host == "gitlab.com" and gitlab_token and gitlab_token.strip():
            active_token = gitlab_token.strip()
            clone_url = f"https://oauth2:{active_token}@gitlab.com/{owner}/{repo}.git"
        elif host == "bitbucket.org" and bitbucket_token and bitbucket_token.strip():
            active_token = bitbucket_token.strip()
            clone_url = f"https://x-token-auth:{active_token}@bitbucket.org/{owner}/{repo}.git"
        else:
            clone_url = f"https://{host}/{owner}/{repo}.git"

        logger.info(f"Cloning repo {owner}/{repo} from {host} (depth=1) into {clone_path}...")

        cmd = ["git", "clone", "--depth", "1", clone_url, clone_path]

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                err_msg = stderr.decode().strip()
                if active_token:
                    err_msg = err_msg.replace(active_token, "******")
                logger.error(f"Git clone failed for {host}/{owner}/{repo}: {err_msg}")
                self.cleanup_clone(clone_path)
                
                # Check for private repository authentication requirement
                is_private_auth = any(term in err_msg.lower() for term in [
                    "authentication failed", "repository not found", "could not read username",
                    "terminal prompts disabled", "http 403", "access denied", "401"
                ])
                
                if is_private_auth and not active_token:
                    raise ClonerError(
                        f"PRIVATE_REPO_AUTH_REQUIRED:{host}:{owner}:{repo}: "
                        f"This repository appears to be private or requires authentication on {host}. "
                        f"Please grant access token permissions for {owner}/{repo}."
                    )
                else:
                    raise ClonerError(f"Git clone failed: {err_msg}")

            logger.info(f"Successfully cloned repo {owner}/{repo} from {host} to {clone_path}")
            return clone_path, owner, repo

        except Exception as e:
            if not isinstance(e, ClonerError):
                logger.exception("Unexpected error during public git clone")
                self.cleanup_clone(clone_path)
                raise ClonerError(f"Unexpected cloner error: {str(e)}")
            raise

    def cleanup_clone(self, clone_path: str):
        """Recursively removes the cloned folder if it is within the temp directory."""
        clone_path = os.path.abspath(clone_path)
        base_dir_abs = os.path.abspath(self.base_dir)

        if not clone_path.startswith(base_dir_abs) or clone_path == base_dir_abs:
            logger.warning(f"Prevented attempt to delete path outside temp clones: {clone_path}")
            return

        if os.path.exists(clone_path):
            try:
                # Remove read-only flags first on Windows if needed, but on macOS simple rmtree is fine.
                shutil.rmtree(clone_path)
                logger.info(f"Cleaned up clone path: {clone_path}")
            except Exception as e:
                logger.error(f"Failed to cleanup clone path {clone_path}: {e}")


# Singleton instance
repo_cloner = RepositoryCloner()
