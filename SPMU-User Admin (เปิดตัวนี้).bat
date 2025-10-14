@echo off
cd /d "%~dp0"
py -m streamlit run "python-code.py" || python -m streamlit run "python-code.py"
