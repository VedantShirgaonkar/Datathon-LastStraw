# Test Data for Lambda Function

This directory contains test events for the `datathon-kafka-processor` Lambda function.

## Test Files

### 1. lambda_test_event.json (Full MSK Format)
**Use with Lambda**: `aws lambda invoke`

Complete AWS MSK event format with base64-encoded Kafka message. This simulates how Lambda receives events from MSK.

```powershell
aws lambda invoke `
  --function-name datathon-kafka-processor `
  --payload file://test_data/lambda_test_event.json `
  --region ap-south-1 `
  response.json
```

### 2. github_push_simple.json (Decoded GitHub Event)
**Use for local testing or reference**

Human-readable GitHub push event showing:
- 2 commits (bug fix + feature)
- File changes
- Author information
- Repository details

This is what's inside the base64-encoded value in `lambda_test_event.json`.

### 3. jira_issue_test.json (Jira Event)
**Use for Jira integration testing**

Jira issue creation event showing:
- Critical bug report
- Priority and status
- Assignee and reporter
- Labels and components

### 4. notion_page_test.json (Notion Event)
**Use for Notion integration testing**

Notion page creation event showing:
- Meeting notes
- Properties (Title, Status, Tags, Date)
- Creator information

## How to Test Locally

1. **Run the Lambda handler locally** (without deploying):
   ```powershell
   cd agent
   python kafka_consumer.py
   ```
   This uses the sample event in the `__main__` block.

2. **Test with AWS Lambda** (deployed function):
   ```powershell
   # Set environment variables first
   cd deployment
   .\set-env-vars.ps1
   
   # Invoke Lambda
   aws lambda invoke `
     --function-name datathon-kafka-processor `
     --payload file://test_data/lambda_test_event.json `
     --region ap-south-1 `
     response.json
   
   # View response
   cat response.json
   ```

3. **Tail logs in real-time**:
   ```powershell
   aws logs tail /aws/lambda/datathon-kafka-processor --follow --region ap-south-1
   ```

## Event Structure

All events follow this structure:
```json
{
  "event_id": "unique-id",
  "source": "github|jira|notion",
  "event_type": "push|jira:issue_created|page_created",
  "timestamp": "2026-02-08T12:00:00Z",
  "raw": {
    // Original event payload from source system
  }
}
```

Lambda MSK events wrap this in:
```json
{
  "eventSource": "aws:kafka",
  "records": {
    "topic-partition": [
      {
        "value": "<base64-encoded-event>",
        ...
      }
    ]
  }
}
```

## What the Agent Does

The agent processes these events and:

1. **Validates** the event structure
2. **Analyzes** the content (commits, issues, pages)
3. **Stores** data in:
   - PostgreSQL (structured data)
   - Neo4j (relationships)
   - ClickHouse (analytics)
4. **Generates** embeddings for semantic search (Pinecone)
5. **Returns** summary and actions taken

## Troubleshooting

**Import errors**: Redeploy with updated dependencies:
```powershell
cd deployment
.\deploy_lambda_docker.ps1 -UpdateCode
```

**Environment variable errors**: Set them:
```powershell
cd deployment
.\set-env-vars.ps1
```

**No logs**: Log group is created on first execution. Invoke once to create it.
