# EC2 Deployment Guide (Amazon Linux)

## Quick Deploy Steps

### 1. Launch EC2 Instance (AWS Console)

1. Go to **AWS Console** → **EC2** → **Launch Instance**
2. Settings:
   - **Name**: `data-extraction-api`
   - **AMI**: Amazon Linux 2023 or Ubuntu Server 22.04 LTS
   - **Instance type**: `t3.micro` (Free tier)
   - **Key pair**: Create new → Download `.pem` file
   - **Security Group**: Allow ports 22, 80, 443

3. Launch and note the **Public IP**

### 2. Upload Code to EC2

```bash
# From your local machine (in data-extraction-api folder)
# Ensure your key file has correct permissions
chmod 400 deploy/data-api-key.pem

# Create tarball for transfer
tar --exclude='venv' --exclude='__pycache__' --exclude='.git' -czf data-api.tar.gz .

# Upload to EC2 (use ec2-user for Amazon Linux, ubuntu for Ubuntu)
scp -i deploy/data-api-key.pem -o StrictHostKeyChecking=no data-api.tar.gz ec2-user@<EC2_IP>:~/
```

### 3. Connect and Run Setup

```bash
# SSH into EC2
ssh -i deploy/data-api-key.pem ec2-user@<EC2_IP>

# Run setup
mkdir -p data-extraction-api
tar -xzf data-api.tar.gz -C data-extraction-api
cd data-extraction-api
chmod +x deploy/setup.sh
./deploy/setup.sh
```

### 4. Configure .env on EC2

```bash
nano ~/data-extraction-api/.env
# Add your credentials, then Ctrl+X, Y, Enter

# Restart the service
sudo systemctl restart data-api
```

### 5. Test

```bash
curl http://<EC2_IP>/health
```

## Webhook URLs

After deployment, configure your webhooks:

- **GitHub**: `http://<EC2_IP>/webhooks/github`
- **Jira**: `http://<EC2_IP>/webhooks/jira`

## Troubleshooting

- **Permissions Error**: Ensure your `.pem` file is the correct one for the instance.
- **Connection Refused**: Check Security Group rules (ports 22, 80, 443 allowed).
- **Service Failed**: Check logs with `sudo journalctl -u data-api -f`.
