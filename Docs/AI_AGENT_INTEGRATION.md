# AI Agent Integration Guide

## Quick Start

Your AI Agent Lambda needs:

- **VPC**: `vpc-0d21a65998db90c76`
- **Security Group**: `sg-0707335f229929c58`
- **Kafka Topics**: `events.github`, `events.jira`, `events.notion`

---

# GitHub Event Schemas (With Email Enrichment)

## Pull Request Event

```json
{
  "event_id": "uuid",
  "source": "github",
  "event_type": "pull_request",
  "timestamp": "2026-02-08T02:00:00Z",
  "raw": {
    "action": "opened",
    "number": 42,
    "pull_request": {
      "title": "Add new feature",
      "body": "Description of changes",
      "state": "open",
      "user": {
        "login": "pr_author_username",
        "email": "pr_author@email.com"
      },
      "head": { "ref": "feature-branch", "sha": "abc123" },
      "base": { "ref": "main" },
      "html_url": "https://github.com/owner/repo/pull/42"
    },
    "_enriched": {
      "user_email": "pr_author@email.com"
    }
  }
}
```

## Issue Event

```json
{
  "event_id": "uuid",
  "source": "github",
  "event_type": "issues",
  "timestamp": "2026-02-08T02:00:00Z",
  "raw": {
    "action": "opened",
    "issue": {
      "number": 15,
      "title": "Bug report",
      "body": "Description of bug",
      "state": "open",
      "user": {
        "login": "issue_creator_username",
        "email": "issue_creator@email.com"
      },
      "labels": [{ "name": "bug" }],
      "html_url": "https://github.com/owner/repo/issues/15"
    },
    "_enriched": {
      "user_email": "issue_creator@email.com"
    }
  }
}
```

## Issue Comment Event

```json
{
  "event_id": "uuid",
  "source": "github",
  "event_type": "issue_comment",
  "timestamp": "2026-02-08T02:00:00Z",
  "raw": {
    "action": "created",
    "issue": {
      "number": 15,
      "title": "Bug report"
    },
    "comment": {
      "body": "I can reproduce this issue",
      "user": {
        "login": "commenter_username",
        "email": "commenter@email.com"
      },
      "html_url": "https://github.com/owner/repo/issues/15#issuecomment-123"
    },
    "_enriched": {
      "user_email": "commenter@email.com"
    }
  }
}
```

## Push Event (Commits)

```json
{
  "event_id": "uuid",
  "source": "github",
  "event_type": "push",
  "timestamp": "2026-02-08T02:00:00Z",
  "raw": {
    "ref": "refs/heads/main",
    "pusher": {
      "name": "username",
      "email": "pusher@email.com"
    },
    "commits": [
      {
        "id": "sha123",
        "message": "Fixed login bug",
        "author": {
          "name": "Author Name",
          "email": "author@email.com"
        },
        "added": ["file.py"],
        "modified": ["other.py"],
        "removed": []
      }
    ],
    "repository": { "name": "repo", "full_name": "owner/repo" }
  }
}
```

---

# Jira Event Schemas

## Issue Created

```json
{
  "source": "jira",
  "event_type": "jira:issue_created",
  "raw": {
    "issue": {
      "key": "PROJ-123",
      "fields": {
        "summary": "Bug title",
        "description": "Details",
        "issuetype": { "name": "Bug" },
        "priority": { "name": "High" },
        "status": { "name": "To Do" },
        "assignee": {
          "displayName": "Assignee",
          "emailAddress": "assignee@email.com"
        },
        "reporter": {
          "displayName": "Reporter",
          "emailAddress": "reporter@email.com"
        }
      }
    }
  }
}
```

## Issue Updated

```json
{
  "source": "jira",
  "event_type": "jira:issue_updated",
  "raw": {
    "issue": { "key": "PROJ-123" },
    "changelog": {
      "items": [
        { "field": "status", "fromString": "To Do", "toString": "Done" }
      ]
    }
  }
}
```

---

# Lambda Handler

```python
import json, base64

def lambda_handler(event, context):
    for topic, records in event['records'].items():
        for record in records:
            data = json.loads(base64.b64decode(record['value']))
            source = data['source']
            raw = data['raw']

            if source == "github":
                # Get user email (enriched)
                email = raw.get("_enriched", {}).get("user_email")

                if data['event_type'] == "pull_request":
                    pr_author = raw['pull_request']['user']['login']
                    pr_author_email = raw['pull_request']['user'].get('email')
                    print(f"PR by {pr_author} ({pr_author_email})")

                elif data['event_type'] == "issues":
                    issue_creator = raw['issue']['user']['login']
                    issue_creator_email = raw['issue']['user'].get('email')
                    print(f"Issue by {issue_creator} ({issue_creator_email})")

                elif data['event_type'] == "issue_comment":
                    commenter = raw['comment']['user']['login']
                    commenter_email = raw['comment']['user'].get('email')
                    print(f"Comment by {commenter} ({commenter_email})")

    return {"status": "ok"}
```

---

# Executor Commands

```python
import boto3, json

lambda_client = boto3.client('lambda', region_name='ap-south-1')

def execute_command(target, action, payload):
    response = lambda_client.invoke(
        FunctionName='datathon-executor',
        Payload=json.dumps({"command": {"target": target, "action": action, "payload": payload}})
    )
    return json.loads(response['Payload'].read())
```

## Jira

```python
execute_command("jira", "create_issue", {"project_key": "PROJ", "summary": "Title", "issue_type": "Bug"})
execute_command("jira", "add_comment", {"issue_key": "PROJ-123", "body": "Comment"})
```

## GitHub

```python
execute_command("github", "create_issue", {"owner": "user", "repo": "repo", "title": "Title"})
execute_command("github", "add_comment", {"owner": "user", "repo": "repo", "issue_number": 1, "body": "Comment"})
```

## Notion

```python
execute_command("notion", "create_page", {"parent_id": "db-id", "title": "Task"})
execute_command("notion", "update_status", {"page_id": "id", "status": "Done"})
execute_command("notion", "assign_task", {"page_id": "id", "assignee": "Name", "priority": "High", "deadline": "2026-02-15"})
```

---

## MSK Connection

```
Brokers: b-1.datathonevents.kzbxr0.c2.kafka.ap-south-1.amazonaws.com:9094,b-2...
Security: TLS/SSL | VPC: vpc-0d21a65998db90c76
```
