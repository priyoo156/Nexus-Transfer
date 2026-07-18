# Render Deployment Guide - Nexus Printing System

## ✅ Setup Complete

Your Flask app is now configured for Render deployment. Here's what was created:

### Files Created:
1. **Procfile** - Tells Render how to start your app using Gunicorn
2. **runtime.txt** - Specifies Python version (3.11.5)
3. **render.yaml** - Complete Render configuration
4. **requirements.txt** - All Python dependencies
5. **.gitignore** - Prevents sensitive files from being committed
6. **app.py** - Updated to handle production mode

## 📋 Deployment Steps

### Step 1: Push to GitHub
```bash
git init
git add .
git commit -m "Add Render deployment configuration"
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git branch -M main
git push -u origin main
```

### Step 2: Create Render Account
- Go to https://render.com
- Sign up with GitHub
- Create new Web Service

### Step 3: Connect Repository
1. Click "New Web Service"
2. Select "Connect a repository"
3. Choose your GitHub repo
4. Render auto-detects `render.yaml`

### Step 4: Set Environment Variables
In Render Dashboard → Environment:

```
SECRET_KEY = your_strong_secret_key_here
FLASK_ENV = production
```

### Step 5: Deploy
Click "Create Web Service" and Render will automatically:
- Install dependencies from requirements.txt
- Run Gunicorn with your Flask app
- Assign a public URL

## ⚠️ Important Considerations

### Database (SQLite)
**⚠️ WARNING**: SQLite on Render is NOT permanent. Every redeploy resets the database.

**For Production:**
1. Use Render PostgreSQL instead (recommended)
2. Add to render.yaml:
```yaml
services:
  - type: pserv
    name: nexus-db
    ipAllowList: []
  
  - type: web
    name: nexus-printing
    env: python
    databaseURL: ${DATABASE_URL}
```

3. Update app.py to use PostgreSQL with psycopg2

### Upload Folder
- Uploads stored in `/uploads/` won't persist after redeploy
- Solution: Use **Render Disk** or external storage (AWS S3, etc.)

To add Render Disk:
```yaml
  - type: web
    name: nexus-printing
    disk:
      name: nexus-uploads
      mountPath: /uploads
      sizeGB: 10
```

### Admin Authentication
Your app uses session-based auth. This works fine on Render, but:
- Sessions are in-memory
- Users get logged out after Render redeploy
- Consider adding persistent session storage

## 🚀 Quick Deployment Checklist

- [ ] Push code to GitHub
- [ ] Create Render account
- [ ] Connect GitHub repository
- [ ] Set `SECRET_KEY` environment variable
- [ ] Deploy and test
- [ ] Set up PostgreSQL if needed
- [ ] Set up Render Disk for uploads if needed

## 📊 Render Plan Comparison

| Feature | Free | Starter | Pro |
|---------|------|---------|-----|
| Runtime | Unlimited | Unlimited | Unlimited |
| Auto Sleep | Yes (after 15 min inactivity) | No | No |
| Database Backup | No | Yes | Yes |
| Support | Community | Email | Premium |
| Price | Free | $7/month | $12/month |

For production use, upgrade from Free plan.

## ✨ Next Steps

1. **Test Locally First:**
```bash
pip install -r requirements.txt
export FLASK_ENV=production
gunicorn app:app
```

2. **Monitor Deployment:**
   - Render Dashboard → Logs
   - Check for errors after deployment

3. **Set Custom Domain:**
   - Render Dashboard → Environment → Add Custom Domain

4. **Enable HTTPS:**
   - Render provides free SSL/TLS automatically

## 🆘 Troubleshooting

**App keeps restarting?**
- Check logs in Render Dashboard
- Verify SECRET_KEY is set
- Ensure requirements.txt has all dependencies

**Database errors?**
- Switch to PostgreSQL (SQLite doesn't persist)
- Check Render Disk is mounted for uploads

**Port errors?**
- app.py now reads PORT from environment automatically
- Render automatically sets PORT=10000

**Static files not showing?**
- Gunicorn needs to serve static files
- Consider using Render's reverse proxy or Nginx

---

For more info: https://render.com/docs
