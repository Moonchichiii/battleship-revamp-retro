@echo off
echo Starting development environment...
docker-compose --profile dev up --build -d
echo Development environment started!
echo Application: http://localhost:8000
echo pgAdmin: http://localhost:5050
echo View logs: docker-compose logs -f
pause
