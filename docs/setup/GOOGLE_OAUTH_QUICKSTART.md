# Google OAuth Quick Start Guide

**Last Updated:** 2026-02-10
**Status:** ✅ All documentation and templates updated with correct variable names

---

## TL;DR

To enable Google Drive, Gmail, Calendar, and Contacts connectors, you need to:

1. **Create OAuth credentials** in Google Cloud Console
2. **Add 4 environment variables** to your `.env` file
3. **Rebuild services** to apply changes

---

## Step 1: Get Google OAuth Credentials

### 1.1 Create Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project: "EchoMind OAuth"
3. Enable these APIs:
   - Google Drive API
   - Gmail API
   - Google Calendar API
   - People API

### 1.2 Configure OAuth Consent Screen

1. Go to **APIs & Services > OAuth consent screen**
2. Choose **External** user type
3. Fill in:
   - **App name:** EchoMind
   - **User support email:** Your email
   - **Authorized domains:** `echomind.ch` (or your domain)
4. Add scopes:
   ```
   https://www.googleapis.com/auth/drive.readonly
   https://www.googleapis.com/auth/drive.metadata.readonly
   https://www.googleapis.com/auth/gmail.readonly
   https://www.googleapis.com/auth/calendar.readonly
   https://www.googleapis.com/auth/contacts.readonly
   ```

### 1.3 Create OAuth Client

1. Go to **APIs & Services > Credentials**
2. Click **Create Credentials > OAuth client ID**
3. Application type: **Web application**
4. Name: `EchoMind Web Client`
5. Add **Authorized redirect URIs**:
   ```
   https://demo.echomind.ch/api/v1/google/auth/callback
   https://localhost/api/v1/google/auth/callback
   ```
   ⚠️ Add one URI per deployment domain (no wildcards supported)
6. Click **Create**
7. **Copy** the Client ID and Client Secret (you'll need them next)

---

## Step 2: Configure Backend

### 2.1 Edit `.env` File

**For local development:**
```bash
cd /Users/gp/Developer/echo-mind/deployment/docker-cluster
nano .env
```

**For production:**
```bash
ssh user@demo.echomind.ch
cd /path/to/echomind/deployment/docker-cluster
nano .env
```

### 2.2 Add These Variables

```bash
# ===============================================
# Google OAuth (for Google Workspace Connectors)
# ===============================================
API_GOOGLE_CLIENT_ID=123456789-abcdefg.apps.googleusercontent.com
API_GOOGLE_CLIENT_SECRET=GOCSPX-your-secret-here
API_GOOGLE_REDIRECT_URI=https://demo.echomind.ch/api/v1/google/auth/callback
API_OAUTH_FRONTEND_URL=https://demo.echomind.ch
```

**Replace:**
- `API_GOOGLE_CLIENT_ID` with your Client ID from Step 1.3
- `API_GOOGLE_CLIENT_SECRET` with your Client Secret from Step 1.3
- `demo.echomind.ch` with your actual domain

**Important Notes:**
- ✅ The `API_` prefix is **required** (Pydantic settings use `env_prefix="API_"`)
- ✅ Use `https://` for production, `http://localhost` for local dev
- ✅ `API_GOOGLE_REDIRECT_URI` must **exactly match** the URI you added in Google Cloud Console
- ❌ Do NOT use `GOOGLE_CLIENT_ID` (missing prefix) - it won't work!

---

## Step 3: Restart Services

### Local Development
```bash
cd deployment/docker-cluster
./cluster.sh -L rebuild
```

### Production (Host Mode)
```bash
cd deployment/docker-cluster
./cluster.sh -H rebuild
```

---

## Step 4: Verify Configuration

### 4.1 Check API Configuration Endpoint

```bash
curl https://demo.echomind.ch/api/v1/google/auth/configured
```

**Expected response:**
```json
{
  "configured": true,
  "message": null
}
```

**If you get `"configured": false`:**
```bash
# Check variables are set
cat .env | grep API_GOOGLE

# Check API logs
docker logs echomind-api -f | grep -i google
```

### 4.2 Test OAuth Flow

1. Open your EchoMind WebUI
2. Go to **Workspace > Connectors**
3. Click **Add Connector**
4. Select **Google Drive**
5. You should see a "Connect to Google" button (not an error message)
6. Click the button - a Google OAuth popup should open
7. Authorize EchoMind
8. Popup should close and connector should show "Connected"

---

## Troubleshooting

### Error: "Google integration is not configured on this server"

**Cause:** Environment variables are missing or incorrect.

**Fix:**
```bash
# 1. Verify variables exist
cat .env | grep API_GOOGLE

# 2. Check for typos (must have API_ prefix!)
grep -E "^API_GOOGLE_CLIENT_ID=" .env
grep -E "^API_GOOGLE_CLIENT_SECRET=" .env
grep -E "^API_GOOGLE_REDIRECT_URI=" .env
grep -E "^API_OAUTH_FRONTEND_URL=" .env

# 3. Ensure no empty values
grep -E "^API_GOOGLE.*=\s*$" .env  # Should return nothing

# 4. Restart services
./cluster.sh -H rebuild
```

### Error: "redirect_uri_mismatch"

**Cause:** Redirect URI in `.env` doesn't match Google Cloud Console.

**Fix:**
1. Check your `.env` file:
   ```bash
   cat .env | grep API_GOOGLE_REDIRECT_URI
   ```
2. Go to [Google Cloud Console > Credentials](https://console.cloud.google.com/apis/credentials)
3. Click your OAuth client
4. Under "Authorized redirect URIs", verify exact match
5. Common mistakes:
   - Trailing slash: `https://demo.echomind.ch/api/v1/google/auth/callback/` ❌
   - HTTP instead of HTTPS: `http://demo.echomind.ch/...` ❌
   - Missing `/api/v1`: `https://demo.echomind.ch/google/auth/callback` ❌

### OAuth works on one domain but not another

**Cause:** Each domain needs its own redirect URI in Google Cloud Console.

**Fix:**
1. Go to [Google Cloud Console > Credentials](https://console.cloud.google.com/apis/credentials)
2. Click your OAuth client
3. Under "Authorized redirect URIs", click **+ Add URI**
4. Add: `https://new-domain.echomind.ch/api/v1/google/auth/callback`
5. Click **Save**
6. Update the new server's `.env` file with the same credentials

---

## Security Best Practices

1. **Never commit `.env`** to version control (it's gitignored)
2. **Rotate secrets every 90 days:**
   - Go to Google Cloud Console > Credentials
   - Click "Add secret" on your OAuth client
   - Update all `.env` files
   - Delete old secret
3. **Use read-only scopes** (already configured in this guide)
4. **Monitor quota usage:**
   - Go to Google Cloud Console > APIs & Services > Dashboard
   - Each API has 10,000 requests/day limit

---

## Summary of Changes (2026-02-10)

### Fixed Files

✅ `deployment/docker-cluster/.env` - Added Google OAuth section
✅ `deployment/docker-cluster/.env.example` - Added template with API_ prefix
✅ `deployment/docker-cluster/.env.host` - Added template with API_ prefix
✅ `docs/setup/google-oauth-setup.md` - Fixed all variable names to use API_ prefix
✅ `docs/user-guides/connecting-google-services.md` - Updated error message with correct variable names
✅ `docs/setup/google-oauth-limitations.md` - Fixed variable names in examples
✅ `docs/integrations/google-oauth-architecture.md` - Fixed API_OAUTH_FRONTEND_URL reference

### Variable Name Reference

| ❌ Old (Incorrect) | ✅ New (Correct) |
|-------------------|------------------|
| `GOOGLE_CLIENT_ID` | `API_GOOGLE_CLIENT_ID` |
| `GOOGLE_CLIENT_SECRET` | `API_GOOGLE_CLIENT_SECRET` |
| `GOOGLE_REDIRECT_URI` | `API_GOOGLE_REDIRECT_URI` |
| `OAUTH_FRONTEND_URL` | `API_OAUTH_FRONTEND_URL` |

**Why the change?** The API service uses `env_prefix="API_"` in its Pydantic settings configuration, so all environment variables must have this prefix.

---

## Full Documentation

For more detailed information, see:
- [Google OAuth Setup Guide](./google-oauth-setup.md) - Full setup instructions
- [Google OAuth Architecture](../integrations/google-oauth-architecture.md) - How it works
- [Google OAuth Limitations](./google-oauth-limitations.md) - Known limitations
- [Connecting Google Services (User Guide)](../user-guides/connecting-google-services.md) - End-user guide

---

**Need Help?**
- Check logs: `docker logs echomind-api -f | grep -i google`
- Verify config: `curl https://your-domain/api/v1/google/auth/configured`
- See [Troubleshooting](#troubleshooting) section above
