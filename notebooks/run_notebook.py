"""Execute a notebook headlessly, in place (outputs saved into the .ipynb).

Usage:  python run_notebook.py c1_clean.ipynb
"""
import sys
import nbformat
from nbclient import NotebookClient

path = sys.argv[1]
nb = nbformat.read(path, as_version=4)
try:
    NotebookClient(nb, timeout=600, kernel_name="python3", resources={"metadata": {"path": "."}}).execute()
finally:
    nbformat.write(nb, path)
print(f"executed {path}")
