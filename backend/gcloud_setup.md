1. Installe gcloud 
 brew install --cask google-cloud-sdk  

 Authenticate to Google
 A.  gcloud auth login
 B. gcloud auth application-default login
 -- Credentials saved to file: [/Users/eboraks/.config/gcloud/application_default_credentials.json]

2. Set-project: gcloud config set project stg-icognition

3. Install sql connector proxy 

4. Connect to DB: cloud-sql-proxy stg-icognition:us-central1:sm-stg-icongition-psql

5. Database credentials
postgres DB
user: postgres / password: Case2214

icog_stg_db
user: icog-stg-user
password: u9b7.GG]zOmu4F$K

 psql -h 127.0.0.1 -p 5432 -U icog-stg-user -d icog_stg_db

export DATABASE_URL=postgresql+psycopg://icog-stg-user:u9b7.GG]zOmu4F$K@127.0.0.1:5432/icog_stg_db
export DATABASE_URL=postgresql+psycopg://app:2214@localhost:5432/icog_dev_db

## Cloud Run Deployment

### Prerequisites
1. Enable Cloud Run API:
   ```bash
   gcloud services enable run.googleapis.com
   ```

2. Grant Cloud Build service account necessary permissions:
   ```bash
   # Cloud Run Admin (allows deploying services)
   gcloud projects add-iam-policy-binding stg-icognition \
     --member="serviceAccount:713863541713@cloudbuild.gserviceaccount.com" \
     --role="roles/run.admin" \
     --condition=None
   
   # Service Account User (allows using service accounts)
   gcloud projects add-iam-policy-binding stg-icognition \
     --member="serviceAccount:713863541713@cloudbuild.gserviceaccount.com" \
     --role="roles/iam.serviceAccountUser" \
     --condition=None
   
   # Secret Manager Accessor (allows accessing secrets like DB_CONNECTION_URL)
   gcloud projects add-iam-policy-binding stg-icognition \
     --member="serviceAccount:713863541713@cloudbuild.gserviceaccount.com" \
     --role="roles/secretmanager.secretAccessor" \
     --condition=None
   ```

3. Grant Cloud Run service account necessary permissions:
   ```bash
   # Secret Accessor role (allows accessing secrets)
   gcloud projects add-iam-policy-binding stg-icognition \
     --member="serviceAccount:713863541713-compute@developer.gserviceaccount.com" \
     --role="roles/secretmanager.secretAccessor" \
     --condition=None
   
   # Cloud SQL Client role (allows connecting to Cloud SQL via Unix socket)
   gcloud projects add-iam-policy-binding stg-icognition \
     --member="serviceAccount:713863541713-compute@developer.gserviceaccount.com" \
     --role="roles/cloudsql.client" \
     --condition=None
   ```

4. Create Secret Manager secrets for all required environment variables:

   **Required Secrets:**
   
   a. **Database Connection** (`DB_CONNECTION_URL`):
   ```bash
   # Store the Cloud SQL connection string in Secret Manager
   # Format for private IP: postgresql+psycopg://user:password@/dbname?host=/cloudsql/PROJECT:REGION:INSTANCE
   # Replace PASSWORD with actual password (URL-encode special characters like $, ], etc.)
   echo -n "postgresql+psycopg://icog-stg-user:u9b7.GG%5DzOmu4F%24K@/icog_stg_db?host=/cloudsql/stg-icognition:us-central1:sm-stg-icongition-psql" | \
     gcloud secrets create DB_CONNECTION_URL --data-file=-
   
   # Or if secret already exists, update it:
   echo -n "postgresql+psycopg://icog-stg-user:u9b7.GG%5DzOmu4F%24K@/icog_stg_db?host=/cloudsql/stg-icognition:us-central1:sm-stg-icongition-psql" | \
     gcloud secrets versions add DB_CONNECTION_URL --data-file=-
   ```
   
   **Note**: URL-encode special characters in passwords:
   - `]` becomes `%5D`
   - `$` becomes `%24`
   - `@` becomes `%40`
   - etc.
   
   b. **Google API Key** (`GOOGLE_API_KEY`) - **REQUIRED**:
   ```bash
   # Get your Google AI API key from: https://aistudio.google.com/apikey
   echo -n "YOUR_GOOGLE_API_KEY_HERE" | \
     gcloud secrets create GOOGLE_API_KEY --data-file=-
   
   # Or update existing:
   echo -n "YOUR_GOOGLE_API_KEY_HERE" | \
     gcloud secrets versions add GOOGLE_API_KEY --data-file=-
   ```
   
   c. **Secret Key** (`SECRET_KEY`) - **REQUIRED for production**:
   ```bash
   # Generate a secure random key (32+ characters recommended)
   # You can generate one with: openssl rand -hex 32
   echo -n "YOUR_SECURE_SECRET_KEY_HERE" | \
     gcloud secrets create SECRET_KEY --data-file=-
   
   # Or update existing:
   echo -n "YOUR_SECURE_SECRET_KEY_HERE" | \
     gcloud secrets versions add SECRET_KEY --data-file=-
   ```
   
   d. **Firebase Service Account** (`FIREBASE_SERVICE_ACCOUNT_JSON`):
   ```bash
   # Copy the entire JSON content from your Firebase service account key file
   # The JSON should be on a single line or properly escaped
   cat path/to/firebase-service-account.json | \
     gcloud secrets create FIREBASE_SERVICE_ACCOUNT_JSON --data-file=-
   
   # Or update existing:
   cat path/to/firebase-service-account.json | \
     gcloud secrets versions add FIREBASE_SERVICE_ACCOUNT_JSON --data-file=-
   ```
   
   e. **Gemini Model Names** (Optional - if you want to override defaults):
   ```bash
   # GEMINI_FLASH_MODEL
   echo -n "models/gemini-2.5-flash" | \
     gcloud secrets create GEMINI_FLASH_MODEL --data-file=-
   
   # GEMINI_FLASH_LITE
   echo -n "models/gemini-2.5-flash-lite" | \
     gcloud secrets create GEMINI_FLASH_LITE --data-file=-
   
   # GEMINI_EMBEDDING_MODEL
   echo -n "models/gemini-embedding-001" | \
     gcloud secrets create GEMINI_EMBEDDING_MODEL --data-file=-
   ```
   
   **Optional Secrets** (only if you use these features):
   
   f. **LangSmith API Key** (`LANGSMITH_API_KEY`) - Only if using LangSmith tracing:
   ```bash
   echo -n "YOUR_LANGSMITH_API_KEY" | \
     gcloud secrets create LANGSMITH_API_KEY --data-file=-
   ```
   
   g. **Hugging Face Token** (`HF_API_TOKEN`) - Only if using Hugging Face features:
   ```bash
   echo -n "YOUR_HF_API_TOKEN" | \
     gcloud secrets create HF_API_TOKEN --data-file=-
   ```
   
   **Verify secrets were created correctly:**
   ```bash
   gcloud secrets versions access latest --secret="DB_CONNECTION_URL"
   gcloud secrets versions access latest --secret="GOOGLE_API_KEY"
   gcloud secrets versions access latest --secret="SECRET_KEY"
   ```

### Build and Deploy

1. From the `backend/` directory, run the Cloud Build:
   ```bash
   cd backend
   gcloud builds submit \
     --config cloudbuild-backend.yaml \
     --substitutions=SHORT_SHA=$(git rev-parse --short HEAD) \
     .
   ```

2. The build process will:
   - Build the Docker image from `backend/Dockerfile`
   - Push the image to `gcr.io/stg-icognition/icognition-backend:SHORT_SHA`
   - Deploy to Cloud Run service `icognition-api` in `us-central1`
   - Configure VPC connector `run-sql-connector` for private Cloud SQL access
   - Set memory to 2Gi, CPU to 2, timeout to 300s, max instances to 20
   - Inject secrets from Secret Manager: `DATABASE_URL`, `FIREBASE_SERVICE_ACCOUNT_JSON`, `GOOGLE_API_KEY`, `SECRET_KEY`, `GEMINI_FLASH_MODEL`, `GEMINI_FLASH_LITE`, `GEMINI_EMBEDDING_MODEL`

### Update Existing Service Resources (If Memory Limit Exceeded)

If you're getting "Memory limit exceeded" errors, update the existing service immediately:

```bash
gcloud run services update icognition-api \
  --region us-central1 \
  --add-cloudsql-instances stg-icognition:us-central1:sm-stg-icongition-psql \
  --memory 2Gi \
  --cpu 2 \
  --timeout 300 \
  --max-instances 20 \
  --min-instances 0 \
  --concurrency 80
```

**Important**: The `--add-cloudsql-instances` flag is required for Cloud Run to establish Unix socket connections to Cloud SQL. Without it, the service cannot connect to the database.

**Note**: The default memory limit is 512 MiB, which may not be enough for AI processing workloads. The configuration above sets it to 2Gi (2048 MiB) and 2 CPUs to handle document processing and AI operations efficiently.

### Cloud Build Configuration

The `cloudbuild-backend.yaml` file:
- Builds from `backend/Dockerfile` (uses `uv` for dependency management)
- Deploys to Cloud Run with VPC connector for private IP Cloud SQL access
- Uses substitution variables: `_SERVICE_NAME`, `_REGION`, `_VPC_CONNECTOR`

### Manual Deployment (Alternative)

If you need to deploy manually without Cloud Build:
```bash
# Build the image
docker build -t gcr.io/stg-icognition/icognition-backend:latest -f backend/Dockerfile backend/

# Push to GCR
docker push gcr.io/stg-icognition/icognition-backend:latest

# Deploy to Cloud Run
gcloud run deploy icognition-api \
  --image gcr.io/stg-icognition/icognition-backend:latest \
  --region us-central1 \
  --platform managed \
  --vpc-connector run-sql-connector \
  --vpc-egress private-ranges-only \
  --add-cloudsql-instances stg-icognition:us-central1:sm-stg-icongition-psql \
  --memory 2Gi \
  --cpu 2 \
  --timeout 300 \
  --max-instances 20 \
  --min-instances 0 \
  --concurrency 80 \
  --set-secrets DATABASE_URL=DB_CONNECTION_URL:latest,FIREBASE_SERVICE_ACCOUNT_JSON=FIREBASE_SERVICE_ACCOUNT_JSON:latest,GOOGLE_API_KEY=GOOGLE_API_KEY:latest,SECRET_KEY=SECRET_KEY:latest,GEMINI_FLASH_MODEL=GEMINI_FLASH_MODEL:latest,GEMINI_FLASH_LITE=GEMINI_FLASH_LITE:latest,GEMINI_EMBEDDING_MODEL=GEMINI_EMBEDDING_MODEL:latest \
  --allow-unauthenticated
```

### Verify Deployment

1. Check Cloud Run service status:
   ```bash
   gcloud run services describe icognition-api --region us-central1
   ```

2. Get the service URL:
   ```bash
   gcloud run services describe icognition-api --region us-central1 --format='value(status.url)'
   ```

3. Test the health endpoint:
   ```bash
   curl https://icognition-api-XXXXX.run.app/health
   ```

### Custom Domain Mapping

To map a custom domain (e.g., `stg.api.icognition.ai`) to your Cloud Run service:

1. **Map the domain in Cloud Run:**
   ```bash
   gcloud run domain-mappings create \
     --service icognition-api \
     --domain stg.api.icognition.ai \
     --region us-central1
   ```

2. **Get the DNS records to add:**
   ```bash
   gcloud run domain-mappings describe stg.api.icognition.ai --region us-central1
   ```
   
   This will show you the DNS records you need to add. You'll typically see something like:
   ```
   resourceRecords:
   - name: stg.api.icognition.ai
     rrdata: ghs.googlehosted.com
     type: CNAME
   ```

3. **Add DNS records in GoDaddy:**
   - Log in to GoDaddy Domain Manager
   - Go to DNS Management for `icognition.ai`
   - Add a CNAME record:
     - **Type**: CNAME
     - **Name**: `stg.api` (or `stg.api.icognition.ai` depending on GoDaddy's interface)
     - **Value**: `ghs.googlehosted.com`
     - **TTL**: 600 (or default)

4. **Verify the mapping:**
   ```bash
   gcloud run domain-mappings describe stg.api.icognition.ai --region us-central1
   ```
   
   Wait for the status to show `ACTIVE` (can take 5-15 minutes for DNS propagation).

5. **Test the custom domain:**
   ```bash
   curl https://stg.api.icognition.ai/
   ```

**Note**: Cloud Run automatically provisions and manages SSL certificates for custom domains, so HTTPS will work automatically once DNS propagates.

---

## Frontend Deployment (Firebase Hosting)

### Prerequisites
1. **Firebase CLI installed**:
   ```bash
   npm install -g firebase-tools
   ```

2. **Firebase project initialized**:
   ```bash
   cd frontend
   firebase login
   firebase init hosting
   ```
   - Select existing Firebase project
   - Set public directory to `dist`
   - Configure as single-page app (yes)
   - Don't overwrite `firebase.json` (if it exists)

3. **Environment configuration**:
   - Created `.env.staging` file in `frontend/` directory:
     ```
     VITE_APP_API_BASE_URL=https://stg.api.icognition.ai
     VITE_WS_BASE_URL=wss://stg.api.icognition.ai
     ```
   - Updated `frontend/src/config/api.ts` to use `VITE_APP_API_BASE_URL` (was `VITE_API_BASE_URL`)

4. **Add backend domain to Firebase Auth** (if using authentication):
   - Go to Firebase Console → Authentication → Settings → Authorized domains
   - Add `stg.api.icognition.ai` to authorized domains

### Manual Deployment Steps

1. **Build the frontend for staging**:
   ```bash
   cd frontend
   npm ci
   npm run build -- --mode staging
   ```
   This creates a `dist/` folder with the production build using staging environment variables.

2. **Deploy to Firebase Hosting**:
   ```bash
   firebase deploy --only hosting --project <your-firebase-project-id>
   ```
   Replace `<your-firebase-project-id>` with your actual Firebase project ID.

3. **Verify deployment**:
   - Check Firebase Console → Hosting for the deployment status
   - Visit the Firebase Hosting URL to verify the frontend loads
   - Test API connectivity by checking browser console for API calls to `https://stg.api.icognition.ai`

### Notes
- The build uses `--mode staging` to load `.env.staging` file
- Frontend is configured to connect to `https://stg.api.icognition.ai` for API calls
- WebSocket connections use `wss://stg.api.icognition.ai` (secure WebSocket)
- `firebase.json` is already configured with SPA rewrite rules (all routes → `/index.html`)
