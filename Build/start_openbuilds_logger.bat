@echo off
rem Start the OpenBuilds job logger (saves a .log after every OpenBuilds Control job).
rem Put a shortcut to this file in shell:startup to start it with Windows.
title OpenBuilds Job Logger
cd /d "%~dp0"
python openbuilds_job_logger.py %*
pause
