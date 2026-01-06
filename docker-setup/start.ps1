# iCognition Docker Startup Script for Windows
# This script helps you start the Docker containers easily

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  iCognition Docker Setup" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check if Docker is running
Write-Host "Checking Docker..." -ForegroundColor Yellow
try {
    $dockerVersion = docker --version
    Write-Host "✓ Docker is installed: $dockerVersion" -ForegroundColor Green
} catch {
    Write-Host "✗ Docker is not installed or not in PATH" -ForegroundColor Red
    Write-Host "Please install Docker Desktop for Windows" -ForegroundColor Red
    exit 1
}

# Check if Docker daemon is running
try {
    docker ps | Out-Null
    Write-Host "✓ Docker daemon is running" -ForegroundColor Green
} catch {
    Write-Host "✗ Docker daemon is not running" -ForegroundColor Red
    Write-Host "Please start Docker Desktop" -ForegroundColor Red
    exit 1
}

# Check if .env file exists
Write-Host ""
Write-Host "Checking backend configuration..." -ForegroundColor Yellow
if (Test-Path "../backend/.env") {
    Write-Host "✓ Backend .env file found" -ForegroundColor Green
} else {
    Write-Host "⚠ Backend .env file not found" -ForegroundColor Yellow
    Write-Host "  Make sure you have configured backend/.env with your cloud database URL" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Starting Docker containers..." -ForegroundColor Yellow
Write-Host ""

# Start containers
docker-compose up --build

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Containers started!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Access the application:" -ForegroundColor Cyan
Write-Host "  Frontend: http://localhost:8080" -ForegroundColor White
Write-Host "  Backend:  http://localhost:8000" -ForegroundColor White
Write-Host "  API Docs: http://localhost:8000/docs" -ForegroundColor White
Write-Host ""
Write-Host "To stop containers, press Ctrl+C or run:" -ForegroundColor Yellow
Write-Host "  docker-compose down" -ForegroundColor White
Write-Host ""

