@echo off
python -m pip install -r requirements.txt
if errorlevel 1 pause & exit /b 1
start "" http://127.0.0.1:8080
python app.py
pause
