import os
import sys

# Ensure the root of the project is in Python's path so we can import src
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.cli.runner import CLIApp

if __name__ == "__main__":
    CLIApp.main()
