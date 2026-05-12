import re

with open("app/tools.py", "r") as f:
    content = f.read()

# Add list_reminders, delete_reminder, pause_reminder, resume_reminder, update_reminder to tools
# Also change set_reminder to use UUID
