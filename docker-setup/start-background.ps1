# iCognition Docker Startup Script (Background Mode) for Windows
# This script starts the Docker containers in detached mode

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  iCognition Docker Setup (Background)" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check if Docker is running
Write-Host "Checking Docker..." -ForegroundColor Yellow
try {
    docker ps | Out-Null
    Write-Host "✓ Docker daemon is running" -ForegroundColor Green
} catch {
    Write-Host "✗ Docker daemon is not running" -ForegroundColor Red
    Write-Host "Please start Docker Desktop" -ForegroundColor Red
    exit 1
}

# Check if .env file exists
if (Test-Path "../backend/.env") {
    Write-Host "✓ Backend .env file found" -ForegroundColor Green
} else {
    Write-Host "⚠ Backend .env file not found" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Starting Docker containers in background..." -ForegroundColor Yellow
Write-Host ""

# Start containers in detached mode
docker-compose up -d --build

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Containers started in background!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Access the application:" -ForegroundColor Cyan
Write-Host "  Frontend: http://localhost:8080" -ForegroundColor White
Write-Host "  Backend:  http://localhost:8000" -ForegroundColor White
Write-Host "  API Docs: http://localhost:8000/docs" -ForegroundColor White
Write-Host ""
Write-Host "Useful commands:" -ForegroundColor Yellow
Write-Host "  View logs:    docker-compose logs -f" -ForegroundColor White
Write-Host "  Stop:         docker-compose down" -ForegroundColor White
Write-Host "  Restart:      docker-compose restart" -ForegroundColor White
Write-Host "  Status:       docker-compose ps" -ForegroundColor White
Write-Host ""

