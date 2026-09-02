@echo off
cd /d "%~dp0"
python -m pip install -e ".[dev]"
if errorlevel 1 pause

