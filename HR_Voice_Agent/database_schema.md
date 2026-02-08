# Engineering Intelligence Platform - Database Schema

This document details the schema of the PostgreSQL database used by the Engineering Intelligence Platform.

## Overview

**Database:** `engineering_intelligence`  
**Host:** `engineering-intelligence1.chwmsemq65p7.ap-south-1.rds.amazonaws.com`

## Tables

### `embeddings`

Stores vector embeddings for various entities (users, code, docs) to enable semantic search and RAG operations.

| Column | Type | Nullable | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary Key |
| `embedding_type` | `varchar` | NO | - | Type of embedding (e.g., 'developer_profile') |
| `source_id` | `uuid` | YES | - | ID of the source entity |
| `source_table` | `varchar` | YES | - | Table name of the source entity |
| `embedding` | `vector` | YES | - | Vector representation (1536 dimensions for OpenAI) |
| `title` | `varchar` | YES | - | Title/Header of the embedded content |
| `content` | `text` | YES | - | Text content that was embedded |
| `metadata` | `jsonb` | YES | - | Additional structured metadata |
| `created_at` | `timestamp` | YES | `now()` | Creation timestamp |
| `updated_at` | `timestamp` | YES | `now()` | Last update timestamp |

**Sample Data:**

```json
[
  {
    "id": "cfcfc220-7b32-4d87-9cac-4bb2c10d4b45",
    "embedding_type": "developer_profile",
    "source_id": "aaaa3333-3333-3333-3333-333333333333",
    "source_table": "users",
    "embedding": "[0.78764087,0.07424241,0.49074... (vector)",
    "title": "Rahul Verma - Developer Profile",
    "content": "Senior developer with expertise in Kubernetes, Terraform, AWS",
    "metadata": "{'role': 'Engineer', 'team': 'Platform Engineering', 'email': 'rahul.verma@company.com'}",
    "created_at": "2026-02-07 12:39:49.008121",
    "updated_at": "2026-02-07 12:39:49.008121"
  },
  {
    "id": "7b8a3ae0-336d-4a63-8059-c4f9ae7b4f88",
    "embedding_type": "developer_profile",
    "source_id": "aaaa2222-2222-2222-2222-222222222222",
    "source_table": "users",
    "embedding": "[0.78764087,0.07424241,0.49074... (vector)",
    "title": "Priya Sharma - Developer Profile",
    "content": "Senior developer with expertise in React, TypeScript, Node.js",
    "metadata": "{'role': 'Tech Lead', 'team': 'Platform Engineering', 'email': 'priya.sharma@company.com'}",
    "created_at": "2026-02-07 12:39:49.008121",
    "updated_at": "2026-02-07 12:39:49.008121"
  }
]
```

### `identity_mappings`

Maps internal user IDs to external system identities (GitHub, Jira, Slack) for data ingestion and correlation.

| Column | Type | Nullable | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary Key |
| `user_id` | `uuid` | YES | - | Foreign Key to `users.id` |
| `source` | `varchar` | NO | - | Source system (github, jira, slack) |
| `external_id` | `varchar` | NO | - | unique ID in external system |
| `external_username`| `varchar` | YES | - | Username/handle in external system |
| `created_at` | `timestamp` | YES | `now()` | Creation timestamp |

**Sample Data:**

```json
[
  {
    "id": "0d1153c1-0a13-4276-bb9b-4825ef413fd6",
    "user_id": "aaaa1111-1111-1111-1111-111111111111",
    "source": "github",
    "external_id": "gh-12345",
    "external_username": "alexkumar",
    "created_at": "2026-02-07 12:37:41.422894"
  },
  {
    "id": "b8acd510-35e1-4440-a95a-bdeaa9a4953d",
    "user_id": "aaaa1111-1111-1111-1111-111111111111",
    "source": "jira",
    "external_id": "jira-alex",
    "external_username": "akumar",
    "created_at": "2026-02-07 12:37:41.422894"
  }
]
```

### `project_assignments`

Junction table linking users to projects with role and allocation details.

| Column | Type | Nullable | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary Key |
| `user_id` | `uuid` | YES | - | Foreign Key to `users.id` |
| `project_id` | `uuid` | YES | - | Foreign Key to `projects.id` |
| `role` | `varchar` | YES | `'contributor'` | Role in the project |
| `allocated_percent`| `numeric` | YES | `100.00` | % of time allocated |
| `assigned_at` | `timestamp` | YES | `now()` | Assignment timestamp |

**Sample Data:**

```json
[
  {
    "id": "62b56ad7-d5ad-443c-be90-2d1edfaacb9f",
    "user_id": "aaaa1111-1111-1111-1111-111111111111",
    "project_id": "a0a01111-1111-1111-1111-111111111111",
    "role": "contributor",
    "allocated_percent": "60.00",
    "assigned_at": "2026-02-07 12:37:51.155248"
  },
  {
    "id": "f053ae69-8b73-42da-8c40-aa1c7c202cd4",
    "user_id": "aaaa2222-2222-2222-2222-222222222222",
    "project_id": "a0a01111-1111-1111-1111-111111111111",
    "role": "lead",
    "allocated_percent": "40.00",
    "assigned_at": "2026-02-07 12:37:51.155248"
  }
]
```

### `projects`

Stores information about engineering projects.

| Column | Type | Nullable | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary Key |
| `name` | `varchar` | NO | - | Project Name |
| `description` | `text` | YES | - | Project description |
| `github_repo` | `varchar` | YES | - | GitHub repository (owner/repo) |
| `jira_project_key` | `varchar` | YES | - | Jira Project Key |
| `notion_database_id`| `varchar` | YES | - | Notion DB ID |
| `status` | `varchar` | YES | `'active'` | Project status |
| `priority` | `varchar` | YES | `'medium'` | Project priority |
| `target_date` | `date` | YES | - | Target completion date |
| `created_at` | `timestamp` | YES | `now()` | Creation timestamp |

**Sample Data:**

```json
[
  {
    "id": "a0a01111-1111-1111-1111-111111111111",
    "name": "API Gateway v2",
    "description": "New microservices API gateway with rate limiting",
    "github_repo": "company/api-gateway-v2",
    "jira_project_key": "APIGW",
    "status": "active",
    "priority": "high",
    "target_date": "2026-03-15",
    "created_at": "2026-02-07 12:37:51.140449"
  },
  {
    "id": "a0a02222-2222-2222-2222-222222222222",
    "name": "Customer Dashboard",
    "description": "React-based customer analytics dashboard",
    "github_repo": "company/customer-dashboard",
    "jira_project_key": "DASH",
    "status": "active",
    "priority": "high",
    "target_date": "2026-02-28",
    "created_at": "2026-02-07 12:37:51.140449"
  }
]
```

### `teams`

Engineering teams/squads.

| Column | Type | Nullable | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary Key |
| `name` | `varchar` | NO | - | Team Name |
| `created_at` | `timestamp` | YES | `now()` | Creation timestamp |

**Sample Data:**

```json
[
  {
    "id": "11111111-1111-1111-1111-111111111111",
    "name": "Platform Engineering",
    "created_at": "2026-02-07 12:37:41.376448"
  },
  {
    "id": "22222222-2222-2222-2222-222222222222",
    "name": "Frontend Team",
    "created_at": "2026-02-07 12:37:41.376448"
  }
]
```

### `users`

Engineering staff and employees.

| Column | Type | Nullable | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `id` | `uuid` | NO | `gen_random_uuid()` | Primary Key |
| `email` | `varchar` | NO | - | Work email |
| `name` | `varchar` | NO | - | Full name |
| `team_id` | `uuid` | YES | - | Foreign Key to `teams.id` |
| `role` | `varchar` | YES | - | Job role/title |
| `hourly_rate` | `numeric` | YES | `50.00` | Hourly cost rate for metrics |
| `created_at` | `timestamp` | YES | `now()` | Creation timestamp |

**Sample Data:**

```json
[
  {
    "id": "aaaa1111-1111-1111-1111-111111111111",
    "email": "alex.kumar@company.com",
    "name": "Alex Kumar",
    "team_id": "11111111-1111-1111-1111-111111111111",
    "role": "Senior Engineer",
    "hourly_rate": "85.00",
    "created_at": "2026-02-07 12:37:41.390250"
  },
  {
    "id": "aaaa2222-2222-2222-2222-222222222222",
    "email": "priya.sharma@company.com",
    "name": "Priya Sharma",
    "team_id": "11111111-1111-1111-1111-111111111111",
    "role": "Tech Lead",
    "hourly_rate": "95.00",
    "created_at": "2026-02-07 12:37:41.390250"
  }
]
```

## Relationships

*   **Teams -> Users**: One-to-Many (`users.team_id` -> `teams.id`)
*   **Users -> Identity Mappings**: One-to-Many (`identity_mappings.user_id` -> `users.id`)
*   **Users <-> Projects**: Many-to-Many via `project_assignments`
*   **Embeddings**: Polymorphic relationship via `source_table` and `source_id`, or loose coupling.
