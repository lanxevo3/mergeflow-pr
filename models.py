from datetime import datetime
from typing import Optional
from sqlmodel import SQLModel, Field, Column, JSON
import uuid

class User(SQLModel, table=True):
    __tablename__ = "users"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    email: str = Field(unique=True, index=True)
    stripe_customer_id: Optional[str] = Field(default=None, index=True)
    stripe_subscription_id: Optional[str] = Field(default=None)
    plan: str = Field(default="free")  # free | individual | team
    github_token_encrypted: Optional[str] = Field(default=None)
    github_username: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = Field(default=True)

class Repo(SQLModel, table=True):
    __tablename__ = "repos"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    full_name: str = Field(index=True)  # e.g. "owner/repo"
    branch: str = Field(default="main")
    min_approvals: int = Field(default=1)
    auto_merge_enabled: bool = Field(default=True)
    notify_on_merge: bool = Field(default=True)
    notify_on_skip: bool = Field(default=False)
    webhook_secret: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=datetime.utcnow)

class MergeLog(SQLModel, table=True):
    __tablename__ = "merge_logs"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    repo_id: str = Field(foreign_key="repos.id", index=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    pr_number: int
    pr_title: str
    pr_url: str
    action: str  # merged | skipped_ci | skipped_review | skipped_draft | error
    reason: Optional[str] = Field(default=None)
    merged_by: Optional[str] = Field(default=None)  # GitHub username or "auto-merge"
    created_at: datetime = Field(default_factory=datetime.utcnow)

class WebhookEvent(SQLModel, table=True):
    __tablename__ = "webhook_events"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    repo_id: str = Field(foreign_key="repos.id", index=True)
    event_type: str  # pull_request, status, check_run, etc.
    payload: str = Field(sa_column=Column(JSON))  # raw event payload
    processed: bool = Field(default=False)
    action_taken: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)
