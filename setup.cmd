@echo off
rem Windows entry point. Runs setup.ps1 with the execution policy bypassed for this one run.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1" %*
