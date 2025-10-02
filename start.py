#!/usr/bin/env python3
import sys
import os

# Add the virtual environment site-packages to Python path
venv_path = os.path.join(os.path.dirname(__file__), '.venv')
if os.path.exists(venv_path):
    python_version = "python3.11"  # Adjust if needed
    site_packages = os.path.join(venv_path, "lib", python_version, "site-packages")
    if os.path.exists(site_packages):
        sys.path.insert(0, site_packages)

# Now import and run your bot
if __name__ == "__main__":
    import bot