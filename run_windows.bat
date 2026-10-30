@echo off
REM MSF Field Library - start script for Windows (double-click).
REM First run: creates .venv, installs requirements (needs internet once) and builds the index if
REM it is missing. Later runs start the app straight away, fully offline. Open http://localhost:8501
cd /d "%~dp0"

set PY=py -3
%PY% --version >nul 2>&1 || set PY=python
%PY% -c "import sys; sys.exit(sys.version_info < (3, 11))" || (
  echo Python 3.11 or newer is required. Install it from python.org and tick "Add Python to PATH".
  pause
  exit /b 1
)

if not exist .venv\Scripts\streamlit.exe (
  echo First run: installing ^(a few minutes, needs internet once^)...
  %PY% -m venv .venv || goto :error
  .venv\Scripts\python -m pip install --upgrade pip || goto :error
  .venv\Scripts\python -m pip install -r requirements.txt || goto :error
)

if not exist index\embeddings.npy (
  echo Building the search index from "D4GC data" ^(downloads the two models once^)...
  .venv\Scripts\python prep.py || goto :error
)

REM Headless: no first-run e-mail question; the browser is opened a few seconds later instead.
echo Starting MSF Field Library at http://localhost:8501 (close this window to stop)
start "" /b cmd /c "timeout /t 6 /nobreak >nul & start http://localhost:8501"
.venv\Scripts\streamlit run app.py --server.headless true --server.port 8501
goto :eof

:error
echo Setup failed - see the messages above.
pause
exit /b 1
