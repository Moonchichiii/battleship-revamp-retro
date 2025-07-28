@echo off 
echo Starting production environment... 
docker-compose up --build -d 
echo Production environment started! 
echo Application: http://localhost:8000 
echo View logs: docker-compose logs -f 
pause 
