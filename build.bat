@echo off

rem call venv\Scripts\activate
call py -m pipenv shell
rem pyInstaller --onefile terminateBiglobeSrv.py
pyInstaller terminateBiglobeSrv.spec
rem move dist\terminateBiglobeSrv.exe dist\terminateBiglobeSrv.exe

pause