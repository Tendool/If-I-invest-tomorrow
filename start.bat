@echo off
rem Starts the Python API (port 8000) and the Next.js UI (port 3000). Ollama must be running (qwen3.5:4b).
cd /d "%~dp0"
start "IfIT API" cmd /k python -m uvicorn ifit.api:app --port 8000
cd web
if not exist node_modules call npm install
start "IfIT Web" cmd /k npm run dev -- -p 3000
echo.
echo   UI : http://localhost:3000
echo   API: http://127.0.0.1:8000/docs
