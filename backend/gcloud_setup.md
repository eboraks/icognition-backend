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

3. Grant Cloud Run service account permission to access secrets:
   ```bash
   # The compute service account (used by Cloud Run) needs Secret Accessor role
   gcloud projects add-iam-policy-binding stg-icognition \
     --member="serviceAccount:713863541713-compute@developer.gserviceaccount.com" \
     --role="roles/secretmanager.secretAccessor" \
     --condition=None
   ```

4. Create Secret Manager secret for database connection:
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
   
   To verify the secret was created correctly:
   ```bash
   gcloud secrets versions access latest --secret="DB_CONNECTION_URL"
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
   - Inject `DATABASE_URL` from Secret Manager

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
  --set-secrets DATABASE_URL=DB_CONNECTION_URL:latest \
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
