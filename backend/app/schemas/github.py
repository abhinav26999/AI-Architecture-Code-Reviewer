from pydantic import BaseModel, HttpUrl
from typing import Optional, List, Dict, Any


class GitHubOwner(BaseModel):
    login: str
    id: int
    avatar_url: HttpUrl
    html_url: HttpUrl


class GitHubRepository(BaseModel):
    id: int
    name: str
    full_name: str
    private: bool
    html_url: HttpUrl
    description: Optional[str] = None
    owner: GitHubOwner


class GitHubPRUser(BaseModel):
    login: str
    id: int
    avatar_url: HttpUrl


class GitHubPRCommitRef(BaseModel):
    label: str
    ref: str
    sha: str
    repo: Optional[GitHubRepository] = None


class GitHubPullRequest(BaseModel):
    id: int
    number: int
    title: str
    state: str
    html_url: HttpUrl
    body: Optional[str] = None
    created_at: str
    updated_at: str
    user: GitHubPRUser
    head: GitHubPRCommitRef
    base: GitHubPRCommitRef
    mergeable: Optional[bool] = None


class GitHubFileChange(BaseModel):
    filename: str
    status: str  # added, modified, removed, renamed
    additions: int
    deletions: int
    changes: int
    patch: Optional[str] = None
    raw_url: HttpUrl
    blob_url: HttpUrl


class GitHubAppTestResponse(BaseModel):
    status: str
    app_id: str
    client_id: str
    authenticated: bool
    message: str
    details: Optional[Dict[str, Any]] = None
