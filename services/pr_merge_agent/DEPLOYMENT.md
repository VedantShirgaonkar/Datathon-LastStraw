# Deploying `pr_merge_agent` to AWS

This guide covers deploying the `pr_merge_agent` using **Docker** on AWS. The architecture consists of:
1.  **API Service**: Hosted on **AWS App Runner** (handles merge webhooks).
2.  **Background Worker**: Hosted on **AWS Lambda** (triggered by **EventBridge Scheduler** to poll for events and send emails).

Both components use the *same* Docker image.

## Prerequisites

-   AWS CLI installed and configured.
-   Docker installed.
-   An AWS ECR (Elastic Container Registry) repository.

---

## 1. Build and Push Docker Image

1.  **Create an ECR Repository** (if not exists):
    ```bash
    aws ecr create-repository --repository-name pr-merge-agent
    ```

2.  **Login to ECR**:
    ```bash
    aws ecr get-login-password --region ap-south-1 | docker login --username AWS --password-stdin 873046390460.dkr.ecr.ap-south-1.amazonaws.com
    ```

3.  **Build and Push**:
    ```bash
    # Set your ECR URI
    export ECR_URI=873046390460.dkr.ecr.ap-south-1.amazonaws.com/pr-merge-agent:latest

    # Build
    docker build --platform linux/amd64 -t $ECR_URI .

    # Push
    docker push $ECR_URI
    ```
    > **Note**: We use `--platform linux/amd64` to ensure compatibility with AWS Lambda and App Runner.

---

## 2. Deploy API (App Runner)
*This service handles the `GET /actions/merge` requests when users click "Merge" in emails.*

1.  Go to **AWS App Runner** console -> **Create service**.
2.  **Source**: "Container registry" -> Select the ECR image you just pushed.
3.  **Deployment triggers**: "Automatic" (redeploys when you push new image).
4.  **Configuration**:
    -   **Runtime**: Python 3
    -   **Port**: `8000`
    -   **Start command**: (Leave empty, it uses the Dockerfile default: `uvicorn ...`)
5.  **Environment Variables**:
    Add the following secrets/config (manage these via AWS Systems Manager Parameter Store or plaintext if non-sensitive):
    -   `CLICKHOUSE_HOST`, `CLICKHOUSE_PORT`, `CLICKHOUSE_USER`, `CLICKHOUSE_PASSWORD`
    -   `GITHUB_TOKEN`
    -   `PR_MERGE_AGENT_SIGNING_SECRET` (Generate a random string: `openssl rand -hex 32`)
    -   `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`
    -   `NEO4J_URI`, `NEO4J_PASSWORD`, etc. (if using Neo4j)

6.  **Create & Deploy**.
7.  **Post-Deployment**: Copy the "Default domain" (e.g., `https://xyz.awsapprunner.com`) and set it as `PR_MERGE_AGENT_BASE_URL` environment variable for the **Worker**.

---

## 3. Deploy Worker (Lambda + EventBridge)
*This background job polls ClickHouse effectively "listening" for new PR events and sends emails.*

### A. Create Lambda Function
1.  Go to **Lambda** console -> **Create function**.
2.  **Container image** -> Select the ECR image.
3.  **Configuration**:
    -   **Timeout**: Increase to `1 min` or more (default is 3s).
    -   **Memory**: `512 MB` should be sufficient.
    -   **Image Config (Override)**:
        -   **CMD**: `pr_merge_agent.runner` (This tells Python to run the runner module).
        *Note: Depending on the base image entrypoint, you might need to set ENTRYPOINT to `python` and CMD to `["-m", "pr_merge_agent.runner"]`.*
4.  **Environment Variables**:
    -   Copy the same variables from App Runner.
    -   **Important**: Set `PR_MERGE_AGENT_BASE_URL` to the App Runner URL (e.g., `https://xyz.awsapprunner.com`).

### B. Schedule with EventBridge
1.  Go to **EventBridge** -> **Schedules** -> **Create schedule**.
2.  **Schedule pattern**: "Recurring schedule" -> "Rate-based" -> e.g., `1 minutes` (or `5 minutes` depending on need).
3.  **Target**: "AWS Lambda" -> Select your `pr-merge-agent-worker` function.
4.  **Create**.

---

## 4. Verification

1.  **Check Worker Logs**: View CloudWatch Logs for the Lambda function. You should see "✅ Emails sent: X" or "Skipping...".
2.  **Test Merge Flow**:
    -   Wait for an email to arrive.
    -   Click the "Merge" button.
    -   Ensure it opens the App Runner URL and shows a success message.
