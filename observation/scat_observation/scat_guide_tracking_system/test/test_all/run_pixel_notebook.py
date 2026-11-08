"""Execute the offline notebook using the observation uv environment."""
import asyncio
import os
from pathlib import Path
import sys

import nbformat
from nbclient import NotebookClient


def main():
    root = Path(__file__).resolve().parents[2]
    path = root / 'test/test_all/pixel_offset_nearby_slit.ipynb'
    os.environ.setdefault('MPLCONFIGDIR', str(root / 'test/test_all/.mplconfig'))
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    notebook = nbformat.read(path, as_version=4)
    NotebookClient(notebook, timeout=120, kernel_name='python3',
                   resources={'metadata': {'path': str(root)}}).execute()
    nbformat.write(notebook, path)
    print(f'Executed notebook: {path}')


if __name__ == '__main__':
    main()
