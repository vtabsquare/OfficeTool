#!/bin/bash
# ============================================================
# VTAB Office Tool — DigitalOcean Droplet Setup Script
# Run this AFTER creating the Droplet and SSHing in as root
# ============================================================

set -e  # Exit on any error

echo "=========================================="
echo "  VTAB Droplet Setup — Step 1: System"
echo "=========================================="

# Update system
apt update && apt upgrade -y

# Install essential packages
apt install -y curl git nginx certbot python3-certbot-nginx \
  python3 python3-pip python3-venv \
  build-essential libpq-dev

# Install Node.js 20 LTS
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt install -y nodejs

# Install PM2 globally
npm install -g pm2

# Verify installations
echo "--- Versions ---"
python3 --version
node --version
npm --version
pm2 --version
nginx -v
echo "----------------"

echo "=========================================="
echo "  Step 2: Create app user"
echo "=========================================="

# Create a non-root user for running the app (more secure)
adduser --disabled-password --gecos "" vtab || true
mkdir -p /var/www/vtab
chown -R vtab:vtab /var/www/vtab

echo "=========================================="
echo "  Step 3: Clone repository"
echo "=========================================="

cd /var/www/vtab
sudo -u vtab git clone https://github.com/Harish-K499/office_tool.git repo
# Now the code is at /var/www/vtab/repo/

# Create symlinks for cleaner paths
ln -sf /var/www/vtab/repo/backend /var/www/vtab/backend
ln -sf /var/www/vtab/repo/socket-server /var/www/vtab/socket-server
ln -sf /var/www/vtab/repo /var/www/vtab/frontend

# Fix ownership
chown -R vtab:vtab /var/www/vtab

echo "=========================================="
echo "  Step 4: Setup Python Backend"
echo "=========================================="

cd /var/www/vtab/backend

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
pip install --upgrade pip
pip install -r requirements.txt

deactivate

echo "=========================================="
echo "  Step 5: Setup Socket Server"
echo "=========================================="

cd /var/www/vtab/socket-server
npm install --production

echo "=========================================="
echo "  Step 6: Build Frontend"
echo "=========================================="

cd /var/www/vtab/frontend
npm install

# Build with production env vars (Vite reads .env.production automatically)
npm run build
# Output is in /var/www/vtab/frontend/dist/

echo "=========================================="
echo "  Step 7: Setup Nginx"
echo "=========================================="

# Remove default site
rm -f /etc/nginx/sites-enabled/default

# Copy nginx config (you'll edit domains later)
cp /var/www/vtab/repo/deploy/nginx.conf /etc/nginx/sites-available/vtab
ln -sf /etc/nginx/sites-available/vtab /etc/nginx/sites-enabled/vtab

# Test nginx config
nginx -t

# Restart nginx
systemctl restart nginx
systemctl enable nginx

echo "=========================================="
echo "  Step 8: Setup PM2"
echo "=========================================="

# Copy ecosystem config
cp /var/www/vtab/repo/deploy/ecosystem.config.js /var/www/vtab/ecosystem.config.js

echo ""
echo "=========================================="
echo "  SETUP COMPLETE!"
echo "=========================================="
echo ""
echo "NEXT STEPS (manual):"
echo "  1. Create /var/www/vtab/backend/id.env with your secrets"
echo "  2. Create /var/www/vtab/socket-server/.env with socket env vars"
echo "  3. Edit /etc/nginx/sites-available/vtab with your actual domains"
echo "  4. Run: cd /var/www/vtab && pm2 start ecosystem.config.js"
echo "  5. Run: pm2 save && pm2 startup"
echo "  6. Run: certbot --nginx (for SSL)"
echo ""
