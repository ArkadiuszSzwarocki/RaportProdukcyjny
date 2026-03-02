#!/usr/bin/env python3
"""
Live Monitoring Dashboard - shows every click and server activity
Usage: python monitor_logs.py
"""

import os
import time
import sys
from datetime import datetime
from pathlib import Path

LOG_FILE = "logs/debug.log"
LAST_POSITION = 0

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def format_log_line(line):
    """Make log lines more readable"""
    # Color codes
    RESET = '\033[0m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    GREEN = '\033[92m'
    BLUE = '\033[94m'
    
    if 'ERROR' in line or 'EXCEPTION' in line:
        color = RED
        emoji = '❌'
    elif 'WARNING' in line or 'WARN' in line:
        color = YELLOW
        emoji = '⚠️'
    elif 'REQUEST' in line or '>>>' in line:
        color = BLUE
        emoji = '→'
    elif 'RESPONSE' in line or '<<<' in line:
        color = GREEN
        emoji = '←'
    else:
        color = RESET
        emoji = '•'
    
    return f"{emoji} {color}{line}{RESET}"

def display_dashboard():
    """Show live dashboard"""
    global LAST_POSITION
    
    clear_screen()
    print("="*80)
    print("🚀 RaportProdukcyjny LIVE MONITORING DASHBOARD")
    print("="*80)
    print(f"⏱️  Updated: {datetime.now().strftime('%H:%M:%S')}")
    print(f"📁 Log file: {LOG_FILE}")
    print(f"🔗 Server: http://localhost:5000")
    print("="*80)
    
    if not os.path.exists(LOG_FILE):
        print("⏳ Waiting for logs...")
        return
    
    try:
        with open(LOG_FILE, 'r', encoding='utf-8', errors='ignore') as f:
            # Read all lines
            all_lines = f.readlines()
            
            # Show last 20 lines
            recent_lines = all_lines[-20:] if len(all_lines) > 20 else all_lines
            
            print("\n📝 RECENT ACTIVITY (Last 20 lines):\n")
            for line in recent_lines:
                line = line.strip()
                if line:
                    print(format_log_line(line))
            
            # Count specific patterns
            all_text = ''.join(all_lines)
            stats = {
                'Requests': all_text.count('REQUEST'),
                'Responses': all_text.count('RESPONSE'),
                'Errors': all_text.count('ERROR'),
                'Warnings': all_text.count('WARNING'),
            }
            
            print("\n" + "="*80)
            print("📊 SESSION STATISTICS:")
            for key, count in stats.items():
                print(f"   {key}: {count}")
            
            print("\n" + "="*80)
            print("💡 TIP: Every request/response to server is logged above!")
            print("🔄 Auto-refreshing every 2 seconds... (Press Ctrl+C to stop)")
            print("="*80)
            
    except Exception as e:
        print(f"Error reading log: {e}")

if __name__ == "__main__":
    try:
        while True:
            display_dashboard()
            time.sleep(2)
    except KeyboardInterrupt:
        print("\n\n👋 Monitoring stopped")
        sys.exit(0)
