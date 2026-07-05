#!/bin/bash
kill $(pgrep -f "python3.*src.english_agent.bot") 2>/dev/null
sleep 1
: > /home/andres/Documents/EnglishAgent/bot.log
cd /home/andres/Documents/EnglishAgent
nohup python3 -m src.english_agent.bot > bot.log 2>&1 &
echo "Bot PID: $!"
