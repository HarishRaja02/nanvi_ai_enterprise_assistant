# Secrets Rotation & Revocation Guide

> [!CAUTION]
> **CRITICAL ACTION REQUIRED:**
> If any credentials were previously checked into version control, local developer files, or hardcoded into source files (such as the Tavily fallback key or mailbox OAuth tokens), they must be immediately revoked and rotated across all environments.

---

## 1. Credentials Requiring Immediate Revocation & Rotation

| Secret Type | Previous Exposure / Location | Action Required | Priority |
| :--- | :--- | :--- | :--- |
| **Tavily Search API Key** | `services/web_search.py` | Revoke existing key on Tavily dashboard; generate new key; set in deployment environment only. | **CRITICAL** |
| **Google OAuth Client Secret** | Environment configs / Git history | Rotate Client Secret in Google Cloud Console; update OAuth consent screen credentials. | **HIGH** |
| **Google User OAuth Tokens** | `backend/storage/user_email_accounts.json` | Revoke all existing refresh and access tokens in Google Account permissions; users must reconnect via Connections Hub. | **HIGH** |
| **Application Master Encryption Key** | `ENCRYPTION_KEY` | Generate a new 32+ character random key; re-encrypt credentials table if existing data is migrated. | **HIGH** |
| **JWT Secret** | `JWT_SECRET` | Generate a new 32+ character cryptographically secure secret; invalidate existing sessions. | **HIGH** |
| **Database Credentials** | PostgreSQL / Supabase URLs | Rotate database user passwords and connection strings. | **HIGH** |

---

## 2. Step-by-Step Rotation Instructions

### 2.1 Tavily API Key
1. Sign in to your [Tavily Dashboard](https://app.tavily.com).
2. Navigate to **API Keys**.
3. Delete the exposed key (`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`).
4. Generate a new API key.
5. In your production/development host environment, set:
   ```bash
   export TAVILY_API_KEY="tvly-new-..."
   ```

### 2.2 Google Workspace / Gmail OAuth Credentials
1. Open the [Google Cloud Console](https://console.cloud.google.com/apis/credentials).
2. Select your Nanvi project.
3. Under **OAuth 2.0 Client IDs**, select your Web Client.
4. Click **Reset Secret** to invalidate the old `client_secret`.
5. Update `GOOGLE_CLIENT_SECRET` in your secure secrets store (AWS Secrets Manager, GCP Secret Manager, or Vercel Environment Variables).
6. To revoke active refresh tokens that were stored in `user_email_accounts.json`, users must visit [Google Account Security Permissions](https://myaccount.google.com/permissions) and revoke access for the app. Users will re-authenticate through the secure Connections Hub OAuth flow.

### 2.3 Master Encryption Key & JWT Secret
Generate two independent 256-bit cryptographically secure keys:
```bash
python -c "import secrets; print('JWT_SECRET=' + secrets.token_hex(32))"
python -c "import secrets; print('ENCRYPTION_KEY=' + secrets.token_hex(32))"
```
Store these strictly in environment variables or your KMS.

---

## 3. Local Secrets Hygiene

1. Ensure `.env`, `.vercel/.env.preview.local`, and `backend/storage/user_email_accounts.json` are listed in `.gitignore`.
2. Never commit `.env` or files containing live credentials.
3. Use `.env.example` as a template with dummy placeholders only.

---

## 4. Continuous Secret Scanning

Run a local secret scan prior to committing:

```bash
# Using Gitleaks
gitleaks detect --source . --verbose

# Using TruffleHog
trufflehog filesystem .
```

The CI workflow `.github/workflows/ci.yml` includes an automated `gitleaks` job that inspects git history with `--fetch-depth=0` and fails the build if any secrets are discovered.
