@echo off
chcp 65001 >nul 2>nul
title YSFX Sunucu Kopyalama Botu
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1

rem --- Python var mi? ---------------------------------------------------
where py >nul 2>nul
if not errorlevel 1 goto :py

where python >nul 2>nul
if not errorlevel 1 goto :python

echo.
echo  [HATA] Python bulunamadi.
echo  https://www.python.org/downloads/ adresinden kurun.
echo  Kurarken "Add Python to PATH" kutusunu isaretleyin.
echo.
pause
exit /b 1

:py
py -3 "YSFX Sunucu Kopyalama Botu.py"
set "SONUC=%errorlevel%"
goto :son

:python
python "YSFX Sunucu Kopyalama Botu.py"
set "SONUC=%errorlevel%"
goto :son

:son
if "%SONUC%"=="0" goto :temiz
echo.
echo  [!] Program hata ile kapandi - hata kodu %SONUC%. Konsolu inceleyin.
pause
:temiz
exit /b %SONUC%
