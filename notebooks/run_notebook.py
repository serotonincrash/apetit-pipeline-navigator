"""Execute a notebook headlessly, in place (outputs saved into the .ipynb).

The kernel runs in the notebook's own folder, so its relative paths (outputs/, results/,
review/) resolve the same way from any working directory.

Usage, from notebooks/:

    uv run --project ../backend --group notebooks python run_notebook.py c1_clean.ipynb
"""

import sys
from pathlib import Path

import nbformat
from nbclient import NotebookClient

path = Path(sys.argv[1]).resolve()
nb = nbformat.read(path, as_version=4)
try:
    NotebookClient(
        nb, timeout=600, kernel_name="python3", resources={"metadata": {"path": str(path.parent)}}
    ).execute()
finally:
    nbformat.write(nb, path)
print(f"executed {path.name}")
