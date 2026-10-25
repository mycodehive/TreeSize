# Third-party notices

TreeSize Explorer is an independent application. TreeSize is a trademark of JAM Software. This project does not bundle JAM Software code, icons or other product assets.

- **PySide6 / Qt for Python / Shiboken**: Qt Company and contributors. Distributed under applicable LGPLv3/GPL or commercial license terms. This application uses the LGPL distribution and dynamically loaded Qt libraries in an unencrypted directory. Users may replace compatible libraries and debug modifications as allowed by the LGPL. Source and license information: https://www.qt.io/qt-for-python and https://code.qt.io/cgit/pyside/pyside-setup.git/ . Qt source: https://code.qt.io/cgit/qt/ . Exact package versions are pinned in `requirements.txt`.
- **keyring**: Jason R. Coombs and contributors; MIT license. https://github.com/jaraco/keyring . Transitive runtime dependencies retain their own licenses.
- **Python**: Python Software Foundation license. https://docs.python.org/3/license.html .
- **PyInstaller**: GPL with its bootloader exception permitting distribution of bundled applications. https://pyinstaller.org/en/stable/license.html .
- **Pillow**: HPND license; used only during icon generation, not required by the application at runtime. https://pillow.readthedocs.io/en/stable/about.html#license .

The Windows build collects license files shipped by the installed distributions into `third_party_licenses`. Preserve those files and the bundled library layout when redistributing. Build scripts and application source are available in this repository. License texts shipped by a component control over any summary here.
