#!/bin/bash
# ===========================================
# Amazon Linux 2023 / 2 Server Setup Script
# ===========================================

set -e  # Exit on error

echo "=========================================="
echo "  Data Extraction API - Server Setup"
echo "  Target: Amazon Linux (ec2-user)"
echo "=========================================="

# Update system
echo "[1/7] Updating system packages..."
sudo yum update -y

# Install Python and dependencies
echo "[2/7] Installing Python, Git, Nginx..."
sudo yum install -y python3 python3-pip git nginx acl

# Check python version
python3 --version

# Create app directory
echo "[3/7] Setting up application directory..."
APP_DIR="/home/ec2-user/data-extraction-api"
mkdir -p $APP_DIR

# Create virtual environment
echo "[4/7] Creating Python virtual environment..."
cd $APP_DIR
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate

# Install Python packages
echo "[5/7] Installing Python packages..."
pip install --upgrade pip
pip install -r requirements.txt

# Setup systemd service
echo "[6/7] Configuring systemd service..."
sudo cp deploy/data-api.service /etc/systemd/system/
# Update service file to use ec2-user
sudo sed -i 's/User=ubuntu/User=ec2-user/g' /etc/systemd/system/data-api.service
sudo sed -i 's/Group=ubuntu/Group=ec2-user/g' /etc/systemd/system/data-api.service
sudo sed -i 's|/home/ubuntu/|/home/ec2-user/|g' /etc/systemd/system/data-api.service

sudo systemctl daemon-reload
sudo systemctl enable data-api
sudo systemctl restart data-api

# Setup nginx
echo "[7/7] Configuring nginx..."
# Copy our config to conf.d
sudo cp deploy/nginx.conf /etc/nginx/conf.d/data-api.conf

# Rename default nginx.conf to backup if we haven't already
if [ ! -f /etc/nginx/nginx.conf.bak ]; then
    sudo cp /etc/nginx/nginx.conf /etc/nginx/nginx.conf.bak
fi

# We need to ensure the default server is disabled
# Simplest way: Overwrite nginx.conf with a clean basic config using a separate file we upload
# OR just trust the default config but comment out the default server block?
# Amazon Linux default nginx.conf usually includes conf.d/*.conf inside http block.

# Let's write a simple nginx.conf using printf to avoid quote hell
sudo printf "user nginx;\nworker_processes auto;\nerror_log /var/log/nginx/error.log;\npid /run/nginx.pid;\ninclude /usr/share/nginx/modules/*.conf;\n\nevents {\n    worker_connections 1024;\n}\n\nhttp {\n    log_format  main  '\$remote_addr - \$remote_user [\$time_local] \"\$request\" '\n                      '\$status \$body_bytes_sent \"\$http_referer\" '\n                      '\"\$http_user_agent\" \"\$http_x_forwarded_for\"';\n\n    access_log  /var/log/nginx/access.log  main;\n\n    sendfile            on;\n    tcp_nopush          on;\n    tcp_nodelay         on;\n    keepalive_timeout   65;\n    types_hash_max_size 4096;\n\n    include             /etc/nginx/mime.types;\n    default_type        application/octet-stream;\n\n    include /etc/nginx/conf.d/*.conf;\n}\n" > /tmp/nginx.conf
sudo mv /tmp/nginx.conf /etc/nginx/nginx.conf

sudo systemctl enable nginx
sudo systemctl restart nginx

echo ""
echo "=========================================="
echo "  ✅ Deployment Complete!"
echo "=========================================="
echo ""
echo "Your API is now running at:"
echo "  http://$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4)"
