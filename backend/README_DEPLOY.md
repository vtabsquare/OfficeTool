# Deploy to DigitalOcean & Fetch Logs

## 1. Deploy latest code
```bash
# On your local machine (OfficeTool repo)
git pull origin main
# Ensure latest changes are present
git log --oneline -n 3
```

## 2. Sync to DigitalOcean droplet
```bash
# Replace <droplet-ip> with your actual DigitalOcean droplet IP
scp -r . root@<droplet-ip>:/root/OfficeTool/
# Or, if you already have the repo there:
ssh root@<droplet-ip> "cd /root/OfficeTool && git pull origin main"
```

## 3. Restart the backend service
```bash
ssh root@<droplet-ip>
cd /root/OfficeTool
# Example if using systemd
systemctl restart office-tool-backend
# Or if using gunicorn/supervisor directly
pkill -f unified_server.py
nohup python backend/unified_server.py > backend.log 2>&1 &
```

## 4. Fetch live logs (choose one)

### Option A: systemd journal
```bash
ssh root@<droplet-ip> "journalctl -u office-tool-backend -f --lines=100"
```

### Option B: direct log file
```bash
ssh root@<droplet-ip> "tail -f /root/OfficeTool/backend.log"
```

### Option C: recent logs, not following
```bash
ssh root@<droplet-ip> "journalctl -u office-tool-backend --lines=200"
# or
ssh root@<droplet-ip> "cat /root/OfficeTool/backend.log | tail -200"
```

## 5. Filter for comp-off related messages
```bash
ssh root@<droplet-ip> "journalctl -u office-tool-backend | grep -i 'comp-off\|compoff\|compensatory'"
# or with file log
ssh root@<droplet-ip> "cat /root/OfficeTool/backend.log | grep -i 'comp-off\|compoff\|compensatory'"
```

---

### Quick one-liner to deploy + logs
```bash
DROPLET_IP=<your-droplet-ip>
ssh root@$DROPLET_IP "cd /root/OfficeTool && git pull origin main && systemctl restart office-tool-backend && sleep 2 && journalctl -u office-tool-backend -f --lines=50"
```

Replace `<your-droplet-ip>` with your actual IP. If your service name differs, replace `office-tool-backend` accordingly.
