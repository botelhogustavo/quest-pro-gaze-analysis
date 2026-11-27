@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

rem ============================================================
rem  Configuracoes. Ajuste se os seus caminhos forem diferentes.
rem ============================================================
rem  Pasta no headset onde o GazeLogger grava os CSVs
set "REMOTE_DIR=/sdcard/Download"
rem  Pasta no PC onde o pull_data.py salva os arquivos (busca recursiva)
set "LOCAL_DIR=E:\projetos\CBG\eyetracking\data\raw"
rem  1 = apagar sem perguntar, 0 = pedir confirmacao antes
set "AUTO_DELETE=0"
rem  1 = apenas mostrar o que seria apagado, nunca apagar
set "DRY_RUN=0"
rem ============================================================
rem  Somente arquivos chamados gaze_*.csv sao considerados para exclusao.
rem  Um arquivo so e apagado do headset se existir, em algum lugar de
rem  LOCAL_DIR no PC, um arquivo com o mesmo nome e o mesmo tamanho.
rem  Feche o app antes (segure B) para nenhum arquivo estar sendo gravado.
rem ============================================================

if exist .venv\Scripts\activate.bat call .venv\Scripts\activate.bat

rem ---- 1. Copiar do headset -----------------------------------
python src\pull_data.py %*
if errorlevel 1 (
    echo.
    echo [ERRO] O pull_data.py falhou. Nada foi apagado do headset.
    goto :end
)

rem ---- 2. Verificacoes de seguranca ---------------------------
adb get-state >nul 2>&1
if errorlevel 1 (
    echo.
    echo [AVISO] Headset nao detectado pelo adb. Nada foi apagado.
    goto :end
)

if not exist "%LOCAL_DIR%" (
    echo.
    echo [AVISO] LOCAL_DIR nao encontrado: %LOCAL_DIR%
    echo Nada foi apagado. Edite LOCAL_DIR no inicio deste arquivo.
    goto :end
)

rem ---- 3. Comparar cada arquivo do headset com a copia no PC --
set "OK_COUNT=0"
set "KEEP_COUNT=0"

echo.
echo Verificando os arquivos copiados em relacao ao headset...
echo.

for /f "usebackq delims=" %%N in (`adb exec-out "cd %REMOTE_DIR% && ls gaze_*.csv" 2^>nul`) do (
    echo %%N| findstr /r /c:"^gaze_.*\.csv$" >nul
    if not errorlevel 1 (
        set "RSIZE="
        set "LSIZE="
        set "LFILE="
        for /f "delims=" %%Z in ('adb exec-out stat -c %%s "%REMOTE_DIR%/%%N" 2^>nul') do set "RSIZE=%%Z"
        for /f "delims=" %%L in ('dir /s /b "%LOCAL_DIR%\%%N" 2^>nul') do (
            set "LFILE=%%L"
            set "LSIZE=%%~zL"
        )
        if not defined LFILE (
            echo [MANTER] %%N - nao encontrado no PC
            set /a KEEP_COUNT+=1
        ) else if not "!RSIZE!"=="!LSIZE!" (
            echo [MANTER] %%N - tamanho diferente: headset !RSIZE!, PC !LSIZE!
            set /a KEEP_COUNT+=1
        ) else (
            echo [OK]     %%N - !LSIZE! bytes
            set /a OK_COUNT+=1
            set "OK_!OK_COUNT!=%%N"
        )
    )
)

echo.
echo Verificados: %OK_COUNT%   Mantidos no headset: %KEEP_COUNT%

if %OK_COUNT%==0 (
    echo Nada para apagar.
    goto :end
)

if "%DRY_RUN%"=="1" (
    echo [SIMULACAO] Os arquivos verificados acima seriam apagados do headset.
    goto :end
)

rem ---- 4. Confirmar e apagar ----------------------------------
if not "%AUTO_DELETE%"=="1" (
    echo.
    choice /c SN /n /m "Apagar do headset os %OK_COUNT% arquivos verificados? [S/N] "
    if errorlevel 2 (
        echo Cancelado. Nada foi apagado.
        goto :end
    )
)

echo.
for /l %%I in (1,1,%OK_COUNT%) do (
    set "F=!OK_%%I!"
    adb shell rm "%REMOTE_DIR%/!F!" >nul 2>&1
    if errorlevel 1 (
        echo [FALHA] Nao foi possivel apagar !F!
    ) else (
        echo Apagado: !F!
    )
)

:end
echo.
pause
endlocal