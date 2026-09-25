@echo off
title CS2 Robs Farmer - Sessao Fantasma
cd /d "%~dp0.."
echo.
echo ============================================
echo   A INICIAR O FARM NA SESSAO FANTASMA
echo ============================================
echo.
start "" "Robs Farmer Agent.exe"
start "" "steam://rungameid/730"
echo A espera do CS2 abrir (faz login no Steam se pedir - so uma vez)...
:espera
timeout /t 5 /nobreak >nul
tasklist /FI "IMAGENAME eq cs2.exe" 2>nul | find /I "cs2.exe" >nul
if errorlevel 1 goto espera
echo.
echo ============================================================
echo   CS2 ABERTO E FARM PRONTO!
echo.
echo   Agora volta a tua sessao:
echo     Menu Iniciar  --^>  clica no teu avatar/nome (Robs)
echo     e escolhe a tua conta.
echo.
echo   A sessao farmbot fica VIVA em segundo plano, a farmar.
echo ============================================================
pause
