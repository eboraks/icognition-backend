# Deployment Plan – iCognition (Google Cloud)

## Task Priority & Progress

### ✅ Completed
- [x] Cloud SQL (PostgreSQL) provisioned; migrations run with Alembic
- [x] FastAPI backend deployed to Cloud Run (private VPC egress, custom domain `stg.api.icognition.ai`)
- [x] Secrets stored in Secret Manager and injected via Cloud Build/Cloud Run
- [x] Cloud Build config for backend fixed (correct Dockerfile path, build context, secret injection)
- [x] Automated DB migrations integrated into `cloudbuild-backend.yaml`
- [x] IAM permissions configured for Cloud Build service account

### 🔄 In Progress
- [ ] **Task #2: Frontend Manual Deployment** (CURRENT FOCUS)
  - Configure frontend environment to use `https://stg.api.icognition.ai` as API base URL
  - Test manual Firebase deployment
  - Verify frontend connects to staging backend
  - **Goal**: Ensure end-to-end functionality before automation

### 📋 Next Up (Priority Order)
1. **Task #1: Backend CI/CD Automation**
   - Create Cloud Build trigger (GitHub → Cloud Build)
   - Test full pipeline: build → migrate → deploy

2. **Task #3: Frontend CI/CD**
   - Create GitHub Actions workflow for frontend deployment
   - Set up Firebase service account secret in GitHub
   - Test automated frontend deployment

3. **Task #4: Cleanup**
   - Remove/update outdated `.github/workflows/main.yml`

4. **Task #5: Environment Separation**
   - Set up separate staging/production environments
   - Use GitHub environments for deployment approvals

5. **Task #6: Monitoring & Alerts**
   - Set up Cloud Monitoring dashboards
   - Configure alert policies for errors and performance

## Current State (done)
- Cloud SQL (PostgreSQL) provisioned; migrations run with Alembic.
- FastAPI backend deployed to Cloud Run (private VPC egress, custom domain `stg.api.icognition.ai`).
- Secrets stored in Secret Manager and injected via Cloud Build/Cloud Run.
- Cloud Build config for backend fixed (correct Dockerfile path, build context, secret injection).

## Remaining Scope
- Automate DB migrations in CI/CD.
- CI/CD for backend (build, migrate, deploy).
- Build and deploy frontend to Firebase Hosting (with Firebase Auth).
- Standardize environment separation (stg/prod) and rollbacks.

## Backend CI/CD (Cloud Build → Cloud Run)
1) Trigger  
   - Create Cloud Build trigger on `main` (and `stg`/`prod` if separate).  
   - Source: GitHub repo, path filter `backend/**`.

2) Build & deploy steps (cloudbuild-backend.yaml)  
   - Build: `docker build -f Dockerfile -t gcr.io/$PROJECT_ID/icognition-backend:$SHORT_SHA .` (run from `backend/`).  
   - Migrate (before deploy): add a step that runs Alembic against Cloud SQL via Cloud SQL Auth Proxy container, using `DATABASE_URL` from Secret Manager. If migrations fail, stop the build.  
   - Deploy: `gcloud run deploy icognition-api --image gcr.io/$PROJECT_ID/icognition-backend:$SHORT_SHA --region us-central1 --vpc-connector run-sql-connector --vpc-egress private-ranges-only --set-secrets DATABASE_URL=DB_CONNECTION_URL:latest,FIREBASE_SERVICE_ACCOUNT_JSON=FIREBASE_SERVICE_ACCOUNT_JSON:latest,GOOGLE_API_KEY=GOOGLE_API_KEY:latest,SECRET_KEY=SECRET_KEY:latest,GEMINI_FLASH_MODEL=GEMINI_FLASH_MODEL:latest,GEMINI_FLASH_LITE=GEMINI_FLASH_LITE:latest,GEMINI_EMBEDDING_MODEL=GEMINI_EMBEDDING_MODEL:latest --allow-unauthenticated`.

3) Secrets required  
   - `DB_CONNECTION_URL`, `FIREBASE_SERVICE_ACCOUNT_JSON`, `GOOGLE_API_KEY`, `SECRET_KEY`, `GEMINI_FLASH_MODEL`, `GEMINI_FLASH_LITE`, `GEMINI_EMBEDDING_MODEL` (optional overrides), plus any future API keys.

4) IAM  
   - Cloud Build SA: `roles/run.admin`, `roles/iam.serviceAccountUser`, `roles/secretmanager.secretAccessor`.  
   - Cloud Run runtime SA: `roles/secretmanager.secretAccessor`, `roles/cloudsql.client`.

5) Rollback  
   - Use Cloud Run revisions to roll traffic back to the previous revision if deploy fails.

## Frontend Deploy (Firebase Hosting + Auth)
### Prereqs
- Firebase project created; Hosting enabled; Auth providers configured.
- Add backend domain (`stg.api.icognition.ai`) to Firebase Auth authorized domains.
- Optional: set up a custom domain for the frontend via Firebase Hosting.

### Manual build & deploy (staging)
```bash
cd frontend
npm ci
npm run build
firebase deploy --only hosting --project <your-firebase-project-id>
```
- Ensure `firebase.json` has SPA rewrite to `/index.html`.
- Frontend env should point API base URL to `https://stg.api.icognition.ai`.

### CI/CD (GitHub Actions example)
Trigger: push to `main` affecting `frontend/**`
```yaml
name: Deploy Frontend
on:
  push:
    paths: ['frontend/**']
    branches: [main]
jobs:
  deploy:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: frontend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: 20 }
      - run: npm ci
      - run: npm run build
      - uses: FirebaseExtended/action-hosting-deploy@v0
        with:
          repoToken: ${{ secrets.GITHUB_TOKEN }}
          firebaseServiceAccount: ${{ secrets.FIREBASE_SERVICE_ACCOUNT }}
          channelId: live
          projectId: <firebase-project-id>
```
Secrets in GitHub:
- `FIREBASE_SERVICE_ACCOUNT`: base64 of a Hosting Admin service account JSON.
- `FIREBASE_PROJECT_ID`: your Firebase project ID.

### Environments
- For prod, use a separate Firebase project or Hosting channel; set API base URL to the prod backend domain.

## DB Migrations (automation pattern)
- Add Cloud Build step (before deploy) that:  
  - Runs Cloud SQL Auth Proxy (private IP) in background.  
  - Exports `DATABASE_URL` from Secret Manager.  
  - Runs `alembic upgrade head`.  
  - Fails the build on migration errors.
- Keep migrations in `backend/migrations/versions`; require migrations in PRs that change schema.

## Environments
- Prefer separate Cloud Run services, SQL instances, secrets, and Firebase projects for `stg` vs `prod`.
- Use GitHub environments (or branch-based triggers) to separate deploys.

## Monitoring & Alerts
- Cloud Monitoring dashboard: Cloud Run (latency, 5xx, CPU/mem), Cloud SQL (CPU, connections, storage).  
 - Alerts: Cloud Run 5xx >2% 5m; Cloud SQL CPU >70% 15m; build failures (trigger notifications).  
- Uptime checks for API health and frontend.

## Rollback & DR
- Backend: revert to previous Cloud Run revision; redeploy last known-good image.  
- Frontend: redeploy previous Hosting version (or use preview channels before promoting).  
- DB: rely on Cloud SQL automated backups/PITR; test restores periodically.

