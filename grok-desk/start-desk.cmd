@echo off
rem Lance Grok Desk (utilise par la tache planifiee "Grok Desk").
cd /d "%~dp0.."
if not exist grok-desk\data mkdir grok-desk\data
node grok-desk\src\index.js >> grok-desk\data\desk.log 2>&1
