#!/usr/bin/env python3
"""Send test GitHub webhooks to a webhook endpoint.

Usage examples:
  python scripts/send_webhook.py --url https://... --event push
  python scripts/send_webhook.py --url https://... --event pull_request --secret mysecret
  python scripts/send_webhook.py --url https://... --file mypayload.json --form

This script supports JSON and form-encoded (payload=...) bodies and will
compute the `X-Hub-Signature-256` header when `--secret` is provided.
"""
from __future__ import annotations

import argparse
import json
import hmac
import hashlib
import sys
from typing import Any
from urllib.parse import urlencode

import requests


SAMPLES = {
    "push": {
        "ref": "refs/heads/main",
        "before": "76032ab598c6",
        "after": "6ae1c9b96c78",
        "repository": {"id": 858305569, "name": "LeetcodeProbs", "full_name": "VedantGadge/LeetcodeProbs"},
        "pusher": {"name": "VedantGadge", "email": "vedant.gadgegsis@gmail.com"},
        "commits": [
            {"id": "6ae1c9b96c78", "message": "tstttt", "author": {"name": "Vedant Gadge", "email": "vedant.gadgegsis@gmail.com"}, "added": [], "modified": ["q3.java"], "removed": []}
        ],
        "head_commit": {"id": "6ae1c9b96c78", "message": "tstttt", "timestamp": "2026-02-08T09:52:52+05:30"}
    },
    "pull_request": {
        "action": "opened",
        "number": 42,
        "pull_request": {"title": "Add feature", "body": "Details", "state": "open", "user": {"login": "pr_author", "email": "pr_author@example.com"}, "html_url": "https://github.com/owner/repo/pull/42"}
    },
    "issues": {
        "action": "opened",
        "issue": {"number": 15, "title": "Bug report", "body": "Details", "state": "open", "user": {"login": "issue_creator", "email": "issue_creator@example.com"}, "labels": [{"name": "bug"}], "html_url": "https://github.com/owner/repo/issues/15"}
    },
    "issue_comment": {
        "action": "created",
        "issue": {"number": 15, "title": "Bug report"},
        "comment": {"body": "I can reproduce this", "user": {"login": "commenter", "email": "commenter@example.com"}, "html_url": "https://github.com/owner/repo/issues/15#issuecomment-123"}
    }
}


def make_signature(secret: str, body: bytes) -> str:
    mac = hmac.new(secret.encode('utf-8'), msg=body, digestmod=hashlib.sha256)
    return "sha256=" + mac.hexdigest()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Send test GitHub webhook payloads")
    p.add_argument("--url", required=True, help="Webhook URL (https://.../webhooks/github)")
    p.add_argument("--event", default="push", help="Event type: push,pull_request,issues,issue_comment")
    p.add_argument("--file", help="Path to JSON file to use as payload (overrides sample) ")
    p.add_argument("--secret", help="GitHub webhook secret to sign the payload")
    p.add_argument("--form", action="store_true", help="Send as application/x-www-form-urlencoded with payload=<json>")
    p.add_argument("--pretty", action="store_true", help="Pretty-print JSON responses")
    args = p.parse_args(argv)

    if args.file:
        try:
            with open(args.file, 'r', encoding='utf-8') as fh:
                payload = json.load(fh)
        except Exception as e:
            print(f"Failed to load payload file: {e}")
            return 2
    else:
        payload = SAMPLES.get(args.event)
        if payload is None:
            print(f"Unknown event and no file provided: {args.event}")
            return 2

    # Build body and headers
    headers: dict[str, str] = {"X-GitHub-Event": args.event}

    if args.form:
        # Build urlencoded payload=<json>
        payload_json = json.dumps(payload, separators=(',', ':'), ensure_ascii=False)
        body_str = urlencode({'payload': payload_json})
        body = body_str.encode('utf-8')
        headers['Content-Type'] = 'application/x-www-form-urlencoded'
    else:
        body = json.dumps(payload).encode('utf-8')
        headers['Content-Type'] = 'application/json'

    if args.secret:
        headers['X-Hub-Signature-256'] = make_signature(args.secret, body)

    try:
        resp = requests.post(args.url, data=body, headers=headers, timeout=15)
    except Exception as e:
        print(f"Request failed: {e}")
        return 3

    print(f"Status: {resp.status_code}")
    ct = resp.headers.get('Content-Type','')
    if 'application/json' in ct:
        if args.pretty:
            try:
                print(json.dumps(resp.json(), indent=2))
            except Exception:
                print(resp.text)
        else:
            print(resp.text)
    else:
        print(resp.text)

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
