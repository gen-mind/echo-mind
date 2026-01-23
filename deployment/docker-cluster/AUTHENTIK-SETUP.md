# Authentik Setup for EchoMind

This document explains how Authentik is pre-configured for EchoMind using **Blueprints** - Authentik's native infrastructure-as-code solution.

## Overview

EchoMind uses Authentik as its OIDC identity provider. The setup is **fully automated** using blueprints that create:

1. **OAuth2/OIDC Provider** - Handles authentication for web app and API
2. **Application** - Links the provider to EchoMind
3. **Development User** (optional) - Pre-configured user for quick testing

## How It Works

### Blueprints

Blueprints are YAML files that Authentik automatically discovers and applies on startup. They're located in:

```
deployment/docker-cluster/authentik/blueprints/
├── echomind-oauth2.yaml     # OAuth2 provider + application
└── echomind-dev-user.yaml   # Development user (optional)
```

Authentik watches the `/blueprints/custom` directory and applies changes automatically.

### Auto-Configuration Flow

```
1. Docker Compose starts Authentik containers
2. Authentik discovers blueprints in /blueprints/custom
3. Blueprints create OAuth2 provider + application
4. (Optional) Dev user is created if enabled
5. EchoMind is ready to authenticate users
```

## Deployment Scenarios

### Scenario 1: Ready-to-Go Container (End Users)

For users who just want to run EchoMind without manual configuration:

```bash
# 1. Clone and enter directory
cd deployment/docker-cluster

# 2. Copy and configure environment
cp .env.example .env
# Edit .env - set secure passwords for production

# 3. Start everything
docker compose up -d

# 4. Login immediately with:
#    - URL: http://auth.localhost
#    - Username: echomind (or akadmin)
#    - Password: echomind123 (or your AUTHENTIK_BOOTSTRAP_PASSWORD)
```

**What's pre-configured:**
- OAuth2 provider named "EchoMind OAuth2"
- Application with slug `echo-mind`
- Redirect URIs for localhost development
- Development user `echomind` (if enabled)

### Scenario 2: Developer Setup (Git Clone)

For developers who clone the repo and want to start working:

```bash
# 1. Clone repository
git clone https://github.com/your-org/echomind.git
cd echomind/deployment/docker-cluster

# 2. Copy environment template
cp .env.example .env

# 3. Generate secure secrets
echo "AUTHENTIK_SECRET_KEY=$(openssl rand -base64 32)" >> .env
echo "ECHOMIND_OAUTH_CLIENT_SECRET=$(openssl rand -base64 32)" >> .env

# 4. Create data directories
mkdir -p ../../data/{postgres,authentik/{media,custom-templates,certs},qdrant,minio,nats,traefik/certificates}

# 5. Start services
docker compose up -d

# 6. Wait for Authentik to apply blueprints (~30 seconds)
docker compose logs -f authentik-worker | grep -i blueprint

# 7. Start developing!
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ECHOMIND_OAUTH_CLIENT_ID` | `echomind-client` | OAuth2 client ID |
| `ECHOMIND_OAUTH_CLIENT_SECRET` | `echomind-secret-...` | OAuth2 client secret |
| `ECHOMIND_REDIRECT_URI_WEB` | `http://localhost:5173/callback` | Web app callback URL |
| `ECHOMIND_REDIRECT_URI_API` | `http://localhost:8080/callback` | API callback URL |
| `ECHOMIND_ENABLE_DEV_USER` | `true` | Create dev user on startup |
| `ECHOMIND_DEV_USER_PASSWORD` | `echomind123` | Dev user password |
| `ECHOMIND_DEV_USER_EMAIL` | `dev@echomind.local` | Dev user email |

### Production Configuration

For production deployments:

```bash
# .env - Production settings
ECHOMIND_OAUTH_CLIENT_ID=echomind-prod
ECHOMIND_OAUTH_CLIENT_SECRET=$(openssl rand -base64 32)
ECHOMIND_REDIRECT_URI_WEB=https://app.echomind.example.com/callback
ECHOMIND_REDIRECT_URI_API=https://api.echomind.example.com/callback

# IMPORTANT: Disable dev user in production
ECHOMIND_ENABLE_DEV_USER=false
```

## Default Credentials

### Admin Account

| Field | Value |
|-------|-------|
| Username | `akadmin` |
| Password | Value of `AUTHENTIK_BOOTSTRAP_PASSWORD` |
| URL | http://auth.localhost (or your `AUTHENTIK_DOMAIN`) |

### Development User (if enabled)

| Field | Value |
|-------|-------|
| Username | `echomind` |
| Password | Value of `ECHOMIND_DEV_USER_PASSWORD` (default: `echomind123`) |
| Email | Value of `ECHOMIND_DEV_USER_EMAIL` |

## OAuth2/OIDC Endpoints

Once Authentik is running, these endpoints are available:

| Endpoint | URL |
|----------|-----|
| **Authorization** | `http://auth.localhost/application/o/authorize/` |
| **Token** | `http://auth.localhost/application/o/token/` |
| **UserInfo** | `http://auth.localhost/application/o/userinfo/` |
| **JWKS** | `http://auth.localhost/application/o/echo-mind/jwks/` |
| **OpenID Config** | `http://auth.localhost/application/o/echo-mind/.well-known/openid-configuration` |

### Web App Configuration

For the React web app (`web/.env`):

```bash
VITE_AUTH_ISSUER=http://auth.localhost/application/o/echo-mind/
VITE_AUTH_CLIENT_ID=echomind-client
VITE_AUTH_REDIRECT_URI=http://localhost:5173/callback
```

### API Configuration

For the FastAPI backend:

```bash
API_AUTH_ISSUER=http://auth.localhost/application/o/echo-mind/
API_AUTH_AUDIENCE=echomind-client
API_AUTH_JWKS_URL=http://authentik-server:9000/application/o/echo-mind/jwks/
```

## Customizing Blueprints

### Modifying the OAuth2 Provider

Edit `authentik/blueprints/echomind-oauth2.yaml`:

```yaml
entries:
  - model: authentik_providers_oauth2.oauth2provider
    attrs:
      # Add more redirect URIs
      redirect_uris:
        - url: "http://localhost:5173/callback"
          matching_mode: strict
        - url: "https://app.example.com/callback"  # Add this
          matching_mode: strict

      # Change token validity
      access_token_validity: hours=2  # Default: hours=1
      refresh_token_validity: days=7  # Default: days=30
```

### Disabling the Dev User

Option 1: Set environment variable:
```bash
ECHOMIND_ENABLE_DEV_USER=false
```

Option 2: Delete the blueprint file:
```bash
rm authentik/blueprints/echomind-dev-user.yaml
```

Option 3: Edit the blueprint metadata:
```yaml
metadata:
  labels:
    blueprints.goauthentik.io/instantiate: "false"
```

### Adding Custom Users

Add to `echomind-dev-user.yaml` or create a new blueprint:

```yaml
entries:
  - model: authentik_core.user
    state: present
    identifiers:
      username: custom-user
    attrs:
      name: Custom User
      email: custom@example.com
      password: secure-password
      is_active: true
```

## Troubleshooting

### Blueprints Not Applied

Check worker logs:
```bash
docker compose logs authentik-worker | grep -i blueprint
```

Common issues:
- YAML syntax errors - validate with `yamllint`
- Missing `!Find` references - ensure default flows exist
- Permission issues - check volume mounts

### Reset Authentik Completely

```bash
# Stop services
docker compose down

# Remove Authentik data (keeps PostgreSQL)
rm -rf ../../data/authentik/*

# Restart
docker compose up -d

# Blueprints will be reapplied
```

### Check Blueprint Status

Via Authentik Admin UI:
1. Go to http://auth.localhost/if/admin/
2. Login as `akadmin`
3. Navigate to **Customization > Blueprints**
4. Check status of each blueprint

### OAuth2 Provider Not Found

If the application shows "Provider not found":

1. Check blueprint was applied:
   ```bash
   docker compose exec authentik-server ak list_blueprints
   ```

2. Manually trigger blueprint apply:
   ```bash
   docker compose restart authentik-worker
   ```

3. Verify provider exists in Admin UI under **Applications > Providers**

## Alternative Approaches

### Terraform Provider

For complex deployments or CI/CD pipelines, consider the [Authentik Terraform Provider](https://github.com/goauthentik/terraform-provider-authentik):

```hcl
provider "authentik" {
  url   = "https://auth.example.com"
  token = var.authentik_token
}

resource "authentik_provider_oauth2" "echomind" {
  name               = "echomind"
  client_id          = "echomind-client"
  authorization_flow = data.authentik_flow.default-authorization.id
}
```

### Pre-Built Docker Image

For distributing a fully configured Authentik:

```dockerfile
FROM ghcr.io/goauthentik/server:2025.10.3
COPY blueprints/ /blueprints/custom/
```

## References

- [Authentik Blueprints Documentation](https://docs.goauthentik.io/customize/blueprints)
- [Authentik Automated Install](https://docs.goauthentik.io/install-config/automated-install/)
- [Authentik Terraform Provider](https://github.com/goauthentik/terraform-provider-authentik)
- [OAuth2 Provider Documentation](https://docs.goauthentik.io/add-secure-apps/providers/oauth2/)