@echo off
cd /d F:\ROBOTAI
python -u tools\train_mister_robot.py > tools\train_mister_robot.log 2>&1
echo EXIT CODE: %ERRORLEVEL% >> tools\train_mister_robot.log
