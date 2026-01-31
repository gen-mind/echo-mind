# Authentik Setup for EchoMind

Complete guide to configure Authentik as the identity provider for EchoMind, including Google/Microsoft social login and Portainer integration.

## Table of Contents

1. [Overview](#overview)
2. [Groups and Permissions](#groups-and-permissions)
3. [Initial Authentik Setup](#initial-authentik-setup)
4. [Create OAuth2 Provider for EchoMind](#create-oauth2-provider-for-echomind)
5. [Configure Google Social Login](#configure-google-social-login)
6. [Configure Microsoft Social Login](#configure-microsoft-social-login)
7. [Create Groups](#create-groups)
8. [Configure Admin Approval Flow](#configure-admin-approval-flow)
9. [Configure Portainer OAuth](#configure-portainer-oauth)
10. [Update EchoMind Configuration](#update-echomind-configuration)
11. [Testing](#testing)
12. [Troubleshooting](#troubleshooting)

---

## Overview

EchoMind uses a three-tier permission system:

```
┌─────────────────────────────────────────────────────────────┐
│                    echomind-superadmins                      │
│  Full app + Portainer + Infrastructure (Qdrant, MinIO, etc) │
├─────────────────────────────────────────────────────────────┤
│                      echomind-admins                         │
│           Full app access (Users, Connectors, etc)           │
├─────────────────────────────────────────────────────────────┤
│                     echomind-allowed                         │
│        Chat, Documents (read), Connectors (personal)         │
└─────────────────────────────────────────────────────────────┘
```

**Authentication Flow:**
1. User clicks "Login with Google" or "Login with Microsoft"
2. Authentik federates to the social provider
3. New users are held for admin approval
4. Once approved and added to a group, user can access EchoMind

---

## Groups and Permissions

### echomind-allowed (Basic Users)

| Feature | Access |
|---------|--------|
| Chat | Full access |
| Documents | Read-only |
| Connectors | View all, create personal only |
| Assistants | View only |
| Embeddings | Hidden |
| LLMs | Hidden |
| Users | Hidden |

### echomind-admins (Application Admins)

| Feature | Access |
|---------|--------|
| Chat | Full access |
| Documents | Full access |
| Connectors | Full access |
| Assistants | Full access |
| Embeddings | Hidden |
| LLMs | Hidden |
| Users | Full access |

### echomind-superadmins (Infrastructure Admins)

| Feature | Access |
|---------|--------|
| All EchoMind features | Full access |
| Embeddings | Full access |
| LLMs | Full access (configure OpenAI/Claude/private endpoints) |
| Portainer | Full access |
| Qdrant Dashboard | Full access |
| MinIO Console | Full access |

---

## Initial Authentik Setup

### 1. Access Authentik Admin

After starting the cluster, access Authentik at:

- **URL**: https://auth.demo.echomind.ch
- **Username**: `akadmin`
- **Password**: Value of `AUTHENTIK_BOOTSTRAP_PASSWORD` from `.env`

### 2. Verify Installation

1. Login to the Admin interface
2. Navigate to **System > System Info**
3. Verify version is 2025.10.3 or later

---

## Create OAuth2 Provider for EchoMind

### Step 1: Create the Provider

1. Go to **Applications > Providers**
2. Click **Create**
3. Select **OAuth2/OpenID Provider**
4. Configure:

| Field | Value |
|-------|-------|
| Name | `echomind-web` |
| Authentication flow | `default-authentication-flow` |
| Authorization flow | `default-provider-authorization-explicit-consent` |
| Client type | `Public` |
| Client ID | (auto-generated - copy this!) |
| Redirect URIs | `https://demo.echomind.ch/auth/callback` |
| Signing Key | `authentik Self-signed Certificate` |

5. Under **Advanced protocol settings**:
   - Subject mode: `Based on the User's Email`
   - Include claims in id_token: `Enabled`
   - Scopes: Select `email`, `openid`, `profile`, and `offline_access`

6. Click **Finish**

### Step 2: Create the Application

1. Go to **Applications > Applications**
2. Click **Create**
3. Configure:

| Field | Value |
|-------|-------|
| Name | `EchoMind` |
| Slug | `echomind-web` |
| Provider | `echomind-web` (the provider you just created) |
| Launch URL | `https://demo.echomind.ch` |

4. Click **Create**

### Step 3: Record Important Values

Save these values for later:

```
Client ID: <copy from provider>
Issuer URL: https://auth.demo.echomind.ch/application/o/echomind-web/
JWKS URL: https://auth.demo.echomind.ch/application/o/echomind-web/jwks/
```

---

## Configure Google Social Login

### Step 1: Google Cloud Console Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing one
3. Navigate to **APIs & Services > OAuth consent screen**
4. Configure:
   - User Type: `External` (or `Internal` for Google Workspace)
   - App name: `EchoMind`
   - User support email: your email
   - Authorized domains: `demo.echomind.ch`
   - Developer contact: your email

5. Click **Save and Continue**
6. Add scopes:
   - `userinfo.email`
   - `userinfo.profile`
   - `openid`

7. Click **Save and Continue**

### Step 2: Create OAuth Credentials

1. Go to **APIs & Services > Credentials**
2. Click **Create Credentials > OAuth Client ID**
3. Configure:

| Field | Value |
|-------|-------|
| Application type | `Web application` |
| Name | `Authentik` |
| Authorized redirect URIs | `https://auth.demo.echomind.ch/source/oauth/callback/google/` |

4. Click **Create**
5. **Copy the Client ID and Client Secret**

### Step 3: Create Google Source in Authentik

1. Go to **Directory > Federation and Social login**
2. Click **Create**
3. Select **Google OAuth Source**
4. Configure:

| Field | Value |
|-------|-------|
| Name | `Google` |
| Slug | `google` |
| Consumer Key | (paste Client ID from Google) |
| Consumer Secret | (paste Client Secret from Google) |
| User matching mode | `Link to a user with identical email address` |

5. Under **Flow settings**:
   - Authentication flow: `default-source-authentication`
   - Enrollment flow: `default-source-enrollment`

6. Click **Finish**

---

## Configure Microsoft Social Login

### Step 1: Azure Portal Setup

1. Go to [Azure Portal](https://portal.azure.com/)
2. Navigate to **Microsoft Entra ID > App registrations**
3. Click **New registration**
4. Configure:

| Field | Value |
|-------|-------|
| Name | `Authentik - EchoMind` |
| Supported account types | `Accounts in any organizational directory and personal Microsoft accounts` |
| Redirect URI | `Web` - `https://auth.demo.echomind.ch/source/oauth/callback/microsoft/` |

5. Click **Register**
6. **Copy the Application (client) ID**

### Step 2: Create Client Secret

1. Go to **Certificates & secrets**
2. Click **New client secret**
3. Description: `Authentik`
4. Expires: `24 months` (recommended)
5. Click **Add**
6. **Copy the secret Value immediately** (it won't be shown again)

### Step 3: Configure API Permissions

1. Go to **API permissions**
2. Click **Add a permission**
3. Select **Microsoft Graph > Delegated permissions**
4. Add:
   - `email`
   - `openid`
   - `profile`
   - `User.Read`
5. Click **Grant admin consent** (if you're an admin)

### Step 4: Create Microsoft Source in Authentik

1. Go to **Directory > Federation and Social login**
2. Click **Create**
3. Select **Microsoft OAuth Source**
4. Configure:

| Field | Value |
|-------|-------|
| Name | `Microsoft` |
| Slug | `microsoft` |
| Consumer Key | (paste Application ID from Azure) |
| Consumer Secret | (paste Client Secret from Azure) |
| User matching mode | `Link to a user with identical email address` |

5. Under **Flow settings**:
   - Authentication flow: `default-source-authentication`
   - Enrollment flow: `default-source-enrollment`

6. Click **Finish**

---

## Create Groups

### Step 1: Create the Groups

1. Go to **Directory > Groups**
2. Create three groups:

| Group Name | Notes |
|------------|-------|
| `echomind-allowed` | Basic users |
| `echomind-admins` | Application administrators |
| `echomind-superadmins` | Infrastructure administrators |

For each group:
1. Click **Create**
2. Enter the name exactly as shown
3. Leave other settings as default
4. Click **Create**

### Step 2: Add Users to Groups

1. Go to **Directory > Users**
2. Select a user
3. Go to the **Groups** tab
4. Click **Add to Group**
5. Select the appropriate group

---

## Configure Admin Approval Flow

New users should require admin approval before accessing EchoMind.

### Step 1: Create Approval Prompt Stage

1. Go to **Flows and Stages > Stages**
2. Click **Create**
3. Select **Prompt Stage**
4. Configure:
   - Name: `enrollment-approval-notice`
5. Add a static prompt:
   - Field Key: `approval_notice`
   - Type: `Static`
   - Label: `Your account is pending approval`
   - Placeholder: `An administrator will review your request. You will receive an email once approved.`
6. Click **Create**

### Step 2: Modify Enrollment Flow (Alternative: Manual Approval)

For simplicity, use manual approval:

1. New users sign up via Google/Microsoft
2. They are created but NOT added to any group
3. Admin reviews in **Directory > Users**
4. Admin adds user to appropriate group (`echomind-allowed`, `echomind-admins`, or `echomind-superadmins`)
5. User can now access the application

### Step 3: Configure Application Access Policy

1. Go to **Applications > Applications > EchoMind**
2. Click **Policy/Group Bindings**
3. Click **Bind existing policy/group**
4. Select **Group** and choose `echomind-allowed`
5. Repeat for `echomind-admins` and `echomind-superadmins`
6. Set **Negate**: `No` for all

Now only users in these groups can access EchoMind.

---

## Configure Portainer OAuth

### Step 1: Create Portainer Provider in Authentik

1. Go to **Applications > Providers**
2. Click **Create**
3. Select **OAuth2/OpenID Provider**
4. Configure:

| Field | Value |
|-------|-------|
| Name | `portainer` |
| Authentication flow | `default-authentication-flow` |
| Authorization flow | `default-provider-authorization-explicit-consent` |
| Client type | `Confidential` |
| Client ID | (auto-generated - copy this!) |
| Client Secret | (auto-generated - copy this!) |
| Redirect URIs | `https://portainer.demo.echomind.ch` |

5. Under **Advanced protocol settings**:
   - Scopes: `email`, `openid`, `profile`

6. Click **Finish**

### Step 2: Create Portainer Application

1. Go to **Applications > Applications**
2. Click **Create**
3. Configure:

| Field | Value |
|-------|-------|
| Name | `Portainer` |
| Slug | `portainer` |
| Provider | `portainer` |
| Launch URL | `https://portainer.demo.echomind.ch` |

4. Click **Create**

### Step 3: Restrict Portainer to Superadmins

1. Go to **Applications > Applications > Portainer**
2. Click **Policy/Group Bindings**
3. Click **Bind existing policy/group**
4. Select **Group**: `echomind-superadmins`
5. Set **Negate**: `No`

Now only `echomind-superadmins` can access Portainer.

### Step 4: Configure Portainer

1. Access Portainer at https://portainer.demo.echomind.ch
2. Login with local admin account
3. Go to **Settings > Authentication**
4. Select **OAuth**
5. Choose **Custom**
6. Configure:

| Field | Value |
|-------|-------|
| Client ID | (from Authentik provider) |
| Client Secret | (from Authentik provider) |
| Authorization URL | `https://auth.demo.echomind.ch/application/o/authorize/` |
| Access Token URL | `https://auth.demo.echomind.ch/application/o/token/` |
| Resource URL | `https://auth.demo.echomind.ch/application/o/userinfo/` |
| Redirect URL | `https://portainer.demo.echomind.ch` |
| Logout URL | `https://auth.demo.echomind.ch/application/o/portainer/end-session/` |
| User identifier | `email` |
| Scopes | `email openid profile` |

**Important**: Use spaces (not commas) between scopes!

7. Click **Save settings**

---

## Update EchoMind Configuration

After setting up Authentik, update your `.env` file:

```bash
# ===============================================
# OIDC Settings
# ===============================================
WEB_OIDC_AUTHORITY=https://auth.demo.echomind.ch/application/o/echomind-web/
WEB_OIDC_CLIENT_ID=<paste Client ID from echomind-web provider>
WEB_OIDC_REDIRECT_URI=https://demo.echomind.ch/auth/callback
WEB_OIDC_POST_LOGOUT_REDIRECT_URI=https://demo.echomind.ch
WEB_OIDC_SCOPE=openid profile email offline_access

# ===============================================
# API Authentication
# ===============================================
API_AUTH_ISSUER=https://auth.demo.echomind.ch/application/o/echomind-web/
API_AUTH_AUDIENCE=<paste Client ID from echomind-web provider>
API_AUTH_JWKS_URL=http://authentik-server:9000/application/o/echomind-web/jwks/
```

Then rebuild and restart:

```bash
docker compose -f docker-compose-host.yml build web api
docker compose -f docker-compose-host.yml up -d
```

---

## Testing

### Test 1: Google Login

1. Open https://demo.echomind.ch
2. Click **Login**
3. Click **Login with Google**
4. Complete Google authentication
5. Verify you are redirected back (may see "pending approval" if not in a group)

### Test 2: Microsoft Login

1. Open https://demo.echomind.ch in incognito
2. Click **Login**
3. Click **Login with Microsoft**
4. Complete Microsoft authentication
5. Verify redirect works

### Test 3: Admin Approval

1. Login to Authentik admin
2. Go to **Directory > Users**
3. Find the new user
4. Add them to `echomind-allowed` group
5. User refreshes and can now access the app

### Test 4: Portainer Access

1. Open https://portainer.demo.echomind.ch
2. Click **Login with OAuth**
3. Only `echomind-superadmins` members should succeed
4. Regular users should see "Access Denied"

### Test 5: Permission Levels

| User Group | Expected Access |
|------------|-----------------|
| Not in any group | Cannot access EchoMind |
| echomind-allowed | Chat, Documents (read), Connectors (personal) |
| echomind-admins | Above + Users, full Connectors |
| echomind-superadmins | Everything + Portainer + Embeddings + LLMs |

---

## Troubleshooting

### "Access Denied" after login

**Cause**: User is not in any of the allowed groups.

**Solution**:
1. Go to Authentik Admin > Directory > Users
2. Find the user
3. Add to appropriate group

### Google/Microsoft button not showing

**Cause**: Social source not added to login page.

**Solution**:
1. Go to **Flows and Stages > Flows**
2. Edit `default-authentication-flow`
3. Go to **Stage Bindings**
4. Edit the identification stage
5. Under **Sources**, add Google and Microsoft

### Token expired errors

**Cause**: Silent token renewal not working.

**Solution**:
1. Ensure `offline_access` scope is included
2. Check Authentik provider has refresh tokens enabled
3. Clear browser storage and re-login

### Portainer OAuth "NOT FOUND"

**Cause**: Incorrect URLs or slug mismatch.

**Solution**:
1. Verify Authentik application slug matches URLs
2. Check redirect URI matches exactly
3. Ensure no trailing slashes mismatch

### CORS errors

**Cause**: Authentik CORS not configured for your domain.

**Solution**: Check Traefik CORS middleware in docker-compose includes your domain.

---

## OAuth Endpoints Reference

| Endpoint | URL |
|----------|-----|
| Authorization | `https://auth.demo.echomind.ch/application/o/authorize/` |
| Token | `https://auth.demo.echomind.ch/application/o/token/` |
| UserInfo | `https://auth.demo.echomind.ch/application/o/userinfo/` |
| JWKS (EchoMind) | `https://auth.demo.echomind.ch/application/o/echomind-web/jwks/` |
| JWKS (Portainer) | `https://auth.demo.echomind.ch/application/o/portainer/jwks/` |
| OpenID Config | `https://auth.demo.echomind.ch/application/o/echomind-web/.well-known/openid-configuration` |

---

## References

- [Authentik Google OAuth Documentation](https://docs.goauthentik.io/users-sources/sources/social-logins/google/cloud/)
- [Authentik Microsoft/Entra Documentation](https://docs.goauthentik.io/users-sources/sources/social-logins/entra-id/oauth/)
- [Authentik Portainer Integration](https://integrations.goauthentik.io/hypervisors-orchestrators/portainer/)
- [Portainer OAuth Documentation](https://docs.portainer.io/admin/settings/authentication/oauth)
- [Google Cloud Console](https://console.cloud.google.com/)
- [Azure Portal](https://portal.azure.com/)
