@echo off
echo.
echo ========================
echo Project Management Dashboard
echo ========================
echo.

:: Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.8 or higher from https://www.python.org
    pause
    exit /b 1
)

echo [OK] Python is installed
echo.

:: Install requirements
echo Installing required packages...
pip install -r requirements.txt

if %errorlevel% neq 0 (
    echo.
    echo ERROR: Failed to install packages
    echo Please check the error messages above
    pause
    exit /b 1
)

echo.
echo [OK] All packages installed successfully!
echo.
echo ========================================
echo Dashboard will open in your browser at:
echo http://localhost:8501
echo ========================================
echo.
echo Press Ctrl+C to stop the server
echo.

:: Run the application
streamlit run app.py --server.headless true

pause
