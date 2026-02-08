# Deploying `pr_merge_agent` to AWS EC2

This guide details how to deploy the service to your existing AWS EC2 instance.

## Prerequisites

-   An active AWS EC2 instance (Amazon Linux 2023, Ubuntu, etc.).
-   SSH key (`.pem` file) to access the instance.
-   The public IP or DNS of your instance (e.g., `ec2-1-2-3-4.compute-1.amazonaws.com`).

---

## 1. Prepare Environment Variables

1.  Make sure your local `.env` file is populated with the production values:
    -   `CLICKHOUSE_HOST` (must be accessible from the EC2)
    -   `GITHUB_TOKEN`
    -   `SMTP_HOST`, etc.
    -   `PR_MERGE_AGENT_BASE_URL` should be `http://<YOUR_EC2_PUBLIC_IP>:8000` (or your domain).

---

## 2. Copy Code to EC2

Use `scp` to copy the `pr_merge_agent` directory to your instance.

```bash
# Run this from your local machine (parent directory of pr_merge_agent)
export EC2_HOST=43.205.135.186
export KEY_PATH="../data-extraction-api/deploy/data-api-key.pem"

# 0. Ensure Key Permissions
chmod 400 "$KEY_PATH"

# Copy files (excluding venv and pycache)
rsync -avz -e "ssh -i $KEY_PATH" \
    --exclude '.venv' \
    --exclude '__pycache__' \
    --exclude '.git' \
    ./pr_merge_agent/ ec2-user@$EC2_HOST:~/pr_merge_agent/
```
*Note: Replace `ubuntu@` with `ec2-user@` if using Amazon Linux.*

---

## 3. Run Setup Script on EC2

1.  SSH into your instance:
    ```bash
    ssh -i $KEY_PATH ubuntu@$EC2_HOST
    ```

2.  Go to the directory and run the setup script:
    ```bash
    cd ~/pr_merge_agent
    
    # Make script executable
    chmod +x setup_ec2.sh
    
    # Run setup
    ./setup_ec2.sh
    ```

The script will:
-   Install Python and dependencies.
-   Create virtual environment.
-   Install requirements.
-   Create and start systemd services (`pr-merge-api` and `pr-merge-worker`).

---

## 4. Verification

1.  **Check Service Status**:
    ```bash
    sudo systemctl status pr-merge-api
    sudo systemctl status pr-merge-worker
    ```

2.  **View Logs**:
    ```bash
    # API Logs
    journalctl -u pr-merge-api -f
    
    # Worker Logs
    journalctl -u pr-merge-worker -f
    ```

3.  **Test API**:
    curl http://localhost:8000/healthz
    # Should return {"ok": true}

---

## 5. Security Group (Firewall)
Ensure your EC2 Security Group allows **Inbound TCP Port 8000** so the webhook/merge links are accessible.
