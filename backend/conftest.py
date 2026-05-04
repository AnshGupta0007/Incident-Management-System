import sys
import os

# Ensure `app` package is importable when pytest runs from backend/
sys.path.insert(0, os.path.dirname(__file__))
