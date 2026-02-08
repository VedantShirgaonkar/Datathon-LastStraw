# Webhook Server Setup Guide

## Architecture

**Direct Webhook Flow** (No Kafka):
```
GitHub/Jira/Notion → FastAPI Webhooks → LangGraph Agent → Databases + Executor Tools
```

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Webhook Secrets

Update `.env` file:

```env
# Webhook Configuration
GITHUB_WEBHOOK_SECRET=your_random_secret_here
JIRA_WEBHOOK_SECRET=your_jira_secret_here
WEBHOOK_SERVER_HOST=0.0.0.0
WEBHOOK_SERVER_PORT=8000
```

> **Generate a secure secret**:
> ```bash
> python -c "import secrets; print(secrets.token_urlsafe(32))"
> ```

### 3. Start Webhook Server

```bash
python webhook_server.py
```

Server will start on `http://localhost:8000`

### 4. Test Locally

```bash
# Run test suite
python test_webhooks.py
```

## Webhook Endpoints

### GitHub Webhook
- **URL**: `POST /webhooks/github`
- **Signature**: HMAC SHA-256 in `X-Hub-Signature-256` header
- **Event Type**: `X-GitHub-Event` header
- **Events**: `push`, `pull_request`, `issues`, `issue_comment`, etc.

### Jira Webhook
- **URL**: `POST /webhooks/jira`
- **Auth**: No signature validation (use network firewall)
- **Event Type**: Extracted from `webhookEvent` field
- **Events**: `jira:issue_created`, `jira:issue_updated`, etc.

### Notion Webhook
- **URL**: `POST /webhooks/notion`
- **Auth**: No built-in validation
- **Event Type**: Extracted from `type` field
- **Events**: `page_created`, `page_updated`, `database_updated`

## Configure Source Systems

### GitHub

1. Go to repository → Settings → Webhooks → Add webhook
2. **Payload URL**: `https://your-domain.com/webhooks/github`
3. **Content type**: `application/json`
4. **Secret**: Your `GITHUB_WEBHOOK_SECRET`
5. **Events**: Select events to trigger
   - Pull requests
   - Pushes
   - Issues
   - Issue comments

### Jira

1. Go to Jira → Settings → System → WebHooks
2. **URL**: `https://your-domain.com/webhooks/jira`
3. **Events**: Select events
   - Issue created
   - Issue updated
   - Issue deleted

### Notion

Notion doesn't have native webhooks. Options:

1. **Polling**: Use scheduled job to poll Notion API
2. **Third-party**: Use Zapier/Make.com to forward events
3. **Custom**: Build Notion integration

## Deployment Options

### Option 1: Local Development (Ngrok)

```bash
# Start ngrok tunnel
ngrok http 8000

# Use ngrok URL in webhook config
# Example: https://abc123.ngrok.io/webhooks/github
```

### Option 2: AWS Lambda (Function URLs)

```bash
# Package webhook server
pip install -t deployment/lambda_package fastapi uvicorn

# Deploy to Lambda
# Enable Lambda Function URL
# Configure as webhook endpoint
```

### Option 3: Docker + ECS/EC2

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["python", "webhook_server.py"]
```

```bash
docker build -t webhook-server .
docker run -p 8000:8000 --env-file .env webhook-server
```

## Security Best Practices

1. **GitHub Signature Validation**: Always enabled in server
2. **HTTPS Only**: Use SSL/TLS for webhook URLs
3. **Network Firewall**: Restrict Jira/Notion webhook IPs
4. **Rate Limiting**: Add rate limiting for production
5. **Secret Rotation**: Rotate webhook secrets periodically

## Agent Processing

When a webhook is received:

1. **Signature Validation** (GitHub only)
2. **Event Normalization** → `WebhookEvent` object
3. **Agent Invocation** → LangGraph workflow:
   - Classify event
   - Select tools
   - Execute tools (database writes + executor calls)
   - Generate response
4. **HTTP Response** → Status + actions taken

## Troubleshooting

### Webhook not received

- Check server is running: `curl http://localhost:8000/`
- Check firewall rules
- Verify webhook URL in source system
- Check server logs for errors

### Signature validation fails (GitHub)

- Verify `GITHUB_WEBHOOK_SECRET` matches GitHub config
- Check raw body is not modified before validation
- Ensure secret is URL-safe

### Agent errors

- Check database connections (PostgreSQL, ClickHouse, Neo4j)
- Verify Featherless AI API key
- Check executor Lambda is deployed
- Review server logs for stack traces

## Example Webhook Payloads

See `test_webhooks.py` for complete examples:

- GitHub PR merged
- Jira issue status changed
- Notion page updated

## Monitoring

Monitor webhook delivery in source systems:

- **GitHub**: Repository → Settings → Webhooks → Recent Deliveries
- **Jira**: Check webhook logs in Jira admin
- **Server Logs**: Check `uvicorn` logs for request/response details
