#!/bin/bash

# --- CONFIGURATION ---
# 1. Set the environment variable for the API Key
export FINNHUB_API_KEY='d183tkpr01ql1b4lks8gd183tkpr01ql1b4lks90' # <--- PASTE YOUR API KEY HERE

# 2. Set the full path to your project directory
PROJECT_DIR="/home/gaurav8bmahajan/live-trading/" # <--- CHANGE YourUsername


# --- SCRIPT EXECUTION ---
# Change to the directory where the bot script is located
cd $PROJECT_DIR

# Run the Python bot script using the python version configured for your webapp
/usr/bin/python3.10 $PROJECT_DIR/bot.py # <--- Make sure python version matches your webapp