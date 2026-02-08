from __future__ import annotations

import os
import textwrap
from typing import Any, Dict, List, Optional

import requests


def summarize_pr(pr: Dict[str, Any], files: List[Dict[str, Any]]) -> str:
    """Summarize a PR for an email.

    - If `GROQ_API_KEY` is configured, uses Groq's LLM API.
    - Otherwise falls back to a deterministic heuristic summary.
    """
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if api_key:
        try:
            return _summarize_pr_llm(pr, files, api_key)
        except Exception as e:
            if os.getenv("PR_MERGE_AGENT_SUMMARY_DEBUG", "").strip().lower() in {"1", "true", "yes"}:
                print(f"⚠️ Groq summarization failed, using heuristic fallback: {e}")
            # Always keep a working fallback; email sending should not fail due to summarization.
            pass

    return _summarize_pr_heuristic(pr, files)


def _summarize_pr_heuristic(pr: Dict[str, Any], files: List[Dict[str, Any]]) -> str:
    title = pr.get("title") or "(no title)"
    author = (pr.get("user") or {}).get("login") or "unknown"
    additions = pr.get("additions")
    deletions = pr.get("deletions")
    changed_files = pr.get("changed_files")

    top_files = []
    for f in files[:10]:
        filename = f.get("filename")
        status = f.get("status")
        a = f.get("additions")
        d = f.get("deletions")
        if filename:
            top_files.append(f"- {filename} ({status}, +{a}/-{d})")

    body = (pr.get("body") or "").strip()
    if body:
        body_snip = textwrap.shorten(body.replace("\r", "").replace("\n", " "), width=300, placeholder="…")
    else:
        body_snip = "(no description)"

    return "\n".join(
        [
            f"Title: {title}",
            f"Author: {author}",
            f"Stats: files={changed_files}, +{additions}/-{deletions}",
            "",
            "Description:",
            body_snip,
            "",
            "Top changed files:",
            *(top_files or ["- (could not fetch file list)"]),
        ]
    )


def _summarize_pr_llm(pr: Dict[str, Any], files: List[Dict[str, Any]], api_key: str) -> str:
    model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    timeout_s = float(os.getenv("GROQ_TIMEOUT_S", "30"))
    max_patch_chars = int(os.getenv("GROQ_DIFF_MAX_CHARS", "8000"))

    title = pr.get("title") or "(no title)"
    author = (pr.get("user") or {}).get("login") or "unknown"
    body = (pr.get("body") or "").strip()
    pr_url = pr.get("html_url") or ""

    files_lines: List[str] = []
    patch_lines: List[str] = []
    patch_budget = max_patch_chars
    for f in files[:50]:
        filename = f.get("filename")
        status = f.get("status")
        a = f.get("additions")
        d = f.get("deletions")
        if filename:
            files_lines.append(f"- {filename} ({status}, +{a}/-{d})")

        patch = f.get("patch")
        if filename and patch and patch_budget > 0:
            patch_str = str(patch)
            if len(patch_str) > 1200:
                patch_str = patch_str[:1200] + "\n…(truncated)…"
            block = f"File: {filename}\n{patch_str}\n"
            if len(block) <= patch_budget:
                patch_lines.append(block)
                patch_budget -= len(block)

    prompt = "\n".join(
        [
            "You are a senior tech lead. Summarize this GitHub Pull Request for an approval email.",
            "Focus on WHAT CHANGED IN THE CODE (functions/endpoints/logic/config), not just file stats.",
            "Keep it concise and actionable.",
            "Return plain text EXACTLY in this format:",
            "Brief:",
            "(2-3 sentences, plain English but technical: what changed, where in code, and why it matters)",
            "What changed:",
            "- (3-7 bullets describing the actual code changes)",
            "Impact/Risk:",
            "- (1-3 bullets)",
            "Suggested checks:",
            "- (2-4 bullets: tests to run, areas to review)",
            "",
            f"PR: {title}",
            f"Author: {author}",
            f"URL: {pr_url}",
            "",
            "Description:",
            body or "(no description)",
            "",
            "Changed files:",
            "\n".join(files_lines) if files_lines else "(file list unavailable)",
            "",
            "Diff snippets (may be partial):",
            "\n".join(patch_lines) if patch_lines else "(no diff snippets available)",
        ]
    )

    url = "https://api.groq.com/openai/v1/chat/completions"
    r = requests.post(
        url,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": "You summarize PRs for merge approval."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
        },
        timeout=timeout_s,
    )
    r.raise_for_status()
    data = r.json()
    content: Optional[str] = None
    try:
        content = data["choices"][0]["message"]["content"]
    except Exception:
        content = None
    if not content:
        raise RuntimeError("LLM response missing content")
    return content.strip()
