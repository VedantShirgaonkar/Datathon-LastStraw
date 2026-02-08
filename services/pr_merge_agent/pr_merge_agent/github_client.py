from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

import requests


class GitHubClient:
    def __init__(self, token: str, timeout_s: int = 15):
        self._timeout = timeout_s
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
        )
        if token:
            self._session.headers["Authorization"] = f"Bearer {token}"

    def list_open_prs(self, repo: str, per_page: int = 50) -> List[Dict[str, Any]]:
        owner, name = repo.split("/", 1)
        url = f"https://api.github.com/repos/{owner}/{name}/pulls"
        prs: List[Dict[str, Any]] = []
        page = 1
        while True:
            r = self._session.get(
                url,
                params={"state": "open", "per_page": per_page, "page": page},
                timeout=self._timeout,
            )
            r.raise_for_status()
            batch = r.json()
            if not batch:
                break
            prs.extend(batch)
            if len(batch) < per_page:
                break
            page += 1
        return prs

    def get_pr(self, repo: str, pr_number: int) -> Dict[str, Any]:
        owner, name = repo.split("/", 1)
        url = f"https://api.github.com/repos/{owner}/{name}/pulls/{pr_number}"
        r = self._session.get(url, timeout=self._timeout)
        r.raise_for_status()
        return r.json()

    def get_mergeability(self, repo: str, pr_number: int, retries: int = 5) -> Tuple[Optional[bool], Optional[str]]:
        """GitHub computes mergeable asynchronously; it can be null initially."""
        last_state: Optional[str] = None
        for i in range(retries):
            pr = self.get_pr(repo, pr_number)
            mergeable = pr.get("mergeable")
            mergeable_state = pr.get("mergeable_state")
            last_state = mergeable_state
            if mergeable is not None:
                return bool(mergeable), mergeable_state
            time.sleep(0.6 + i * 0.2)
        return None, last_state

    def get_pr_files(self, repo: str, pr_number: int, per_page: int = 100) -> List[Dict[str, Any]]:
        owner, name = repo.split("/", 1)
        url = f"https://api.github.com/repos/{owner}/{name}/pulls/{pr_number}/files"
        files: List[Dict[str, Any]] = []
        page = 1
        while True:
            r = self._session.get(url, params={"per_page": per_page, "page": page}, timeout=self._timeout)
            r.raise_for_status()
            batch = r.json()
            if not batch:
                break
            files.extend(batch)
            if len(batch) < per_page:
                break
            page += 1
        return files

    def merge_pr(self, repo: str, pr_number: int, *, method: str = "squash") -> Dict[str, Any]:
        owner, name = repo.split("/", 1)
        url = f"https://api.github.com/repos/{owner}/{name}/pulls/{pr_number}/merge"
        r = self._session.put(url, json={"merge_method": method}, timeout=self._timeout)
        # GitHub returns 405/409 etc for non-mergeable
        r.raise_for_status()
        return r.json()
