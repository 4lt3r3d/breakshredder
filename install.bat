@echo off
cd /d "%~dp0"
echo Installing Python packages for BREAKSHREDDER...
python -m pip install --upgrade -r requirements.txt
echo.
echo Done. Now run start.bat
pause
