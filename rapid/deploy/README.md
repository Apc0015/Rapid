# RAPID — Production Deployment

## Quick-start (Ubuntu 22.04 LTS)

### 1. Install system packages
```bash
sudo apt update && sudo apt install -y nginx python3.11 python3.11-venv certbot python3-certbot-nginx
```

### 2. Create app user + directory
```bash
sudo useradd -r -s /bin/false www-data   # already exists on Ubuntu
sudo mkdir -p /opt/rapid
sudo chown www-data:www-data /opt/rapid
```

### 3. Deploy code
```bash
sudo -u www-data git clone https://github.com/YOUR_ORG/rapid /opt/rapid
cd /opt/rapid
sudo -u www-data python3.11 -m venv venv
sudo -u www-data venv/bin/pip install -r rapid/requirements.txt
```

### 4. Configure environment
```bash
sudo -u www-data cp rapid/.env.example rapid/.env
sudo -u www-data nano rapid/.env
# Set: JWT_SECRET_KEY, OPENAI_API_KEY, BACKUP_PROVIDER, etc.
```

### 5. Install SSL certificate
```bash
sudo certbot --nginx -d YOUR_DOMAIN
# Follow prompts — certbot auto-edits nginx.conf for HTTPS
```

### 6. Install Nginx config
```bash
sudo cp rapid/deploy/nginx.conf /etc/nginx/sites-available/rapid
# Edit YOUR_DOMAIN in the file:
sudo sed -i 's/YOUR_DOMAIN/your.domain.com/g' /etc/nginx/sites-available/rapid
sudo ln -s /etc/nginx/sites-available/rapid /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

### 7. Install + start systemd service
```bash
sudo cp rapid/deploy/rapid.service /etc/systemd/system/
# Edit /opt/rapid path if different
sudo systemctl daemon-reload
sudo systemctl enable --now rapid
sudo systemctl status rapid
```

### 8. Verify
```bash
curl https://YOUR_DOMAIN/health
# → {"status":"ok","version":"1.0.0",...}
```

---

## Backup configuration

Set one of these in `.env` (or update via the API at `PUT /backup/config`):

### Local filesystem (default)
```env
BACKUP_PROVIDER=local
BACKUP_LOCAL_DIR=/opt/rapid/backups
BACKUP_KEEP_LOCAL=14
```

### AWS S3
```env
BACKUP_PROVIDER=s3
BACKUP_S3_BUCKET=my-rapid-backups
BACKUP_S3_REGION=eu-west-1
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=...
```

### S3-compatible (MinIO / Backblaze B2)
```env
BACKUP_PROVIDER=s3
BACKUP_S3_BUCKET=my-bucket
BACKUP_S3_ENDPOINT_URL=https://s3.eu-central-003.backblazeb2.com
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
```

### Google Cloud Storage
```env
BACKUP_PROVIDER=gcs
BACKUP_GCS_BUCKET=my-rapid-backups
GOOGLE_APPLICATION_CREDENTIALS=/opt/rapid/gcs-key.json
```

### Azure Blob
```env
BACKUP_PROVIDER=azure
BACKUP_AZURE_CONTAINER=rapid-backups
AZURE_STORAGE_CONNECTION_STRING=DefaultEndpointsProtocol=https;AccountName=...
```

---

## Trigger a backup via API
```bash
curl -X POST https://YOUR_DOMAIN/backup/run \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

---

## Scheduled backups (cron)
```cron
# Daily backup at 02:30 AM
30 2 * * * /opt/rapid/venv/bin/python -c "
import asyncio, sys
sys.path.insert(0, '/opt/rapid/rapid')
from infrastructure.backup_manager import get_backup_manager
asyncio.run(get_backup_manager().run_backup())
"
```
