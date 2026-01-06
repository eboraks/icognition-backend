# Docker Setup for iCognition

This folder contains Docker configuration files to run the iCognition application (backend and frontend) using Docker Compose.

**Note:** This setup does NOT include the database service. You must use a cloud database and configure the connection string in your `.env` file.

## Prerequisites

1. **Docker Desktop for Windows** installed and running
2. **WSL 2** enabled (Docker Desktop will prompt if needed)
3. **Backend `.env` file** configured with your cloud database URL

## Quick Start

### 1. Configure Backend Environment

Make sure your `backend/.env` file contains your cloud database connection string:

```env
DATABASE_URL=postgresql://user:password@your-cloud-db-host:5432/dbname
# ... other environment variables
```

### 2. Build and Start Services

From the `docker-setup` folder, run:

```powershell
# Build and start both services
docker-compose up --build

# Or run in detached mode (background)
docker-compose up -d --build
```

### 3. Access the Application

- **Frontend**: http://localhost:8080
- **Backend API**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/health

## Docker Commands

### Start Services
```powershell
docker-compose up
```

### Start in Background
```powershell
docker-compose up -d
```

### View Logs
```powershell
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f backend
docker-compose logs -f frontend
```

### Stop Services
```powershell
docker-compose down
```

### Rebuild After Code Changes
```powershell
docker-compose up --build
```

### Restart a Specific Service
```powershell
docker-compose restart backend
docker-compose restart frontend
```

## Service Details

### Backend Service
- **Container Name**: `icognition-backend`
- **Port Mapping**: `8000:8080` (host:container)
- **Environment**: Loaded from `backend/.env`
- **Volumes**: 
  - `backend/app` → `/app/app` (for hot-reload)
  - `backend/migrations` → `/app/migrations`

### Frontend Service
- **Container Name**: `icognition-frontend`
- **Port Mapping**: `8080:8080`
- **Environment Variables**:
  - `NODE_ENV=development`
  - `VITE_APP_API_BASE_URL=http://localhost:8000`
- **Volumes**: 
  - `frontend/src` → `/app/src` (for hot-reload)
  - `frontend/public` → `/app/public`
  - `frontend/index.html` → `/app/index.html`

## Development Workflow

### Hot Reload
Both services are configured with volume mounts for hot-reload:
- **Backend**: Changes to `backend/app/` will trigger auto-reload
- **Frontend**: Changes to `frontend/src/` will trigger Vite hot-reload

### Making Changes

1. **Backend Changes**:
   - Edit files in `backend/app/`
   - Backend will auto-reload (if using `--reload` flag)
   - Check logs: `docker-compose logs -f backend`

2. **Frontend Changes**:
   - Edit files in `frontend/src/`
   - Vite will hot-reload automatically
   - Check logs: `docker-compose logs -f frontend`

3. **Dependency Changes**:
   - **Backend**: Rebuild container: `docker-compose up --build backend`
   - **Frontend**: Rebuild container: `docker-compose up --build frontend`

## Troubleshooting

### Port Already in Use

If ports 8000 or 8080 are already in use:

```powershell
# Check what's using the port
netstat -ano | findstr :8000
netstat -ano | findstr :8080

# Kill the process (replace PID with actual process ID)
taskkill /PID <PID> /F
```

Or change the ports in `docker-compose.yml`:
```yaml
ports:
  - "8001:8080"  # Use 8001 instead of 8000
```

### Database Connection Issues

1. Verify your `backend/.env` has the correct `DATABASE_URL`
2. Check that your cloud database is accessible from your network
3. Review backend logs: `docker-compose logs backend`

### Container Won't Start

1. Check logs: `docker-compose logs`
2. Verify Docker Desktop is running
3. Try rebuilding: `docker-compose up --build --force-recreate`

### Frontend Can't Connect to Backend

1. Ensure backend is healthy: `docker-compose ps`
2. Check backend logs: `docker-compose logs backend`
3. Verify `VITE_APP_API_BASE_URL` in frontend environment

### Windows-Specific Issues

1. **Path Issues**: Docker Desktop handles Windows paths automatically
2. **Line Endings**: Git may change line endings; use `.gitattributes` if needed
3. **WSL 2**: Ensure WSL 2 is enabled in Docker Desktop settings

## File Structure

```
docker-setup/
├── docker-compose.yml    # Main Docker Compose configuration
└── README.md            # This file

../backend/
├── Dockerfile           # Backend container definition
└── .env                 # Backend environment variables (not in repo)

../frontend/
└── Dockerfile           # Frontend container definition
```

## Production Considerations

This setup is optimized for **development**. For production:

1. Remove volume mounts (or use read-only)
2. Use production builds instead of development servers
3. Add proper health checks and restart policies
4. Configure proper networking and security
5. Use Docker secrets for sensitive data
6. Set up proper logging and monitoring

## Additional Resources

- [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop/)
- [Docker Compose Documentation](https://docs.docker.com/compose/)
- Backend README: `../backend/README.md`
- Frontend README: `../frontend/README.md`

