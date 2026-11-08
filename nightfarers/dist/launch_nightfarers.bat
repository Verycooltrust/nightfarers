@echo off
rem Nightfarers launcher: starts Elden Ring offline through me3 with only this mod and its own save (NF0000.sl2).
setlocal
cd /d "%~dp0"
set "HERE=%~dp0"

rem --- Find me3 -------------------------------------------------------------
set "ME3="
for /f "delims=" %%i in ('where me3 2^>nul') do if not defined ME3 set "ME3=%%i"
if not defined ME3 if exist "%HERE%me3\bin\me3.exe" set "ME3=%HERE%me3\bin\me3.exe"
if not defined ME3 if exist "%LOCALAPPDATA%\Programs\garyttierney\me3\bin\me3.exe" set "ME3=%LOCALAPPDATA%\Programs\garyttierney\me3\bin\me3.exe"
if not defined ME3 if exist "%ProgramFiles(x86)%\Steam\steamapps\common\ELDEN RING\Game\bin\me3.exe" set "ME3=%ProgramFiles(x86)%\Steam\steamapps\common\ELDEN RING\Game\bin\me3.exe"
if not defined ME3 goto no_me3

rem --- Write the me3 profile (sound loader only if it was installed) --------
set "PROFILE=%HERE%nightfarers.me3"
> "%PROFILE%" echo profileVersion = "v1"
>> "%PROFILE%" echo # Offline only, separate save. Written by launch_nightfarers.bat on every launch.
>> "%PROFILE%" echo start_online = false
>> "%PROFILE%" echo savefile = "NF0000.sl2"
>> "%PROFILE%" echo.
>> "%PROFILE%" echo [[supports]]
>> "%PROFILE%" echo game = "eldenring"
>> "%PROFILE%" echo.
>> "%PROFILE%" echo [[packages]]
>> "%PROFILE%" echo id = "nightfarers"
>> "%PROFILE%" echo path = 'package'
>> "%PROFILE%" echo.
>> "%PROFILE%" echo [[natives]]
>> "%PROFILE%" echo path = 'native/nightfarers_native.dll'

set "SOUND=%HERE%native\sound_loader"
if not exist "%SOUND%\er_sound_bank_loader.dll" goto no_sound
>> "%PROFILE%" echo.
>> "%PROFILE%" echo [[natives]]
>> "%PROFILE%" echo path = 'native/sound_loader/er_sound_bank_loader.dll'

rem The sound loader reads this file from beside its DLL; the bank folder must be a full path.
set "INI=%SOUND%\ersoundbank_loader.ini"
> "%INI%" echo [general]
>> "%INI%" echo enabled=true
>> "%INI%" echo log_enabled=true
>> "%INI%" echo.
>> "%INI%" echo [runtime]
>> "%INI%" echo start_delay_ms=5000
>> "%INI%" echo conditional_enabled=true
>> "%INI%" echo condition_hand=auto
>> "%INI%" echo poll_every_frames=6
>> "%INI%" echo unload_when_inactive=true
>> "%INI%" echo.
>> "%INI%" echo [bank_files]
>> "%INI%" echo memory_copy_enabled=true
>> "%INI%" echo bank_file_dir=%HERE%package\sd\enus
>> "%INI%" echo.
>> "%INI%" echo [fallback_startup_preload]
>> "%INI%" echo retries_per_id=120
>> "%INI%" echo retry_every_frames=60
>> "%INI%" echo.
>> "%INI%" echo [conditional_bank_mappings]
>> "%INI%" echo condition_bank_mapping=290:8990
goto launch

:no_sound
echo Note: ERSoundBankLoader not found in native\sound_loader, so Wylder's own sounds are off. See README.md.

:launch
echo Starting Elden Ring offline with Nightfarers...
"%ME3%" launch -p "%PROFILE%"
if errorlevel 1 goto failed
exit /b 0

:no_me3
echo me3 was not found. Install it from https://github.com/garyttierney/me3/releases
echo (the Windows installer), then run this file again. See README.md.
pause
exit /b 1

:failed
echo me3 could not start the game. The message above says why; see README.md, Troubleshooting.
pause
exit /b 1
