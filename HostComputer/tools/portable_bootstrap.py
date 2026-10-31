import sys
from pathlib import Path


def configure_qt():
    from PyQt5.QtCore import QCoreApplication
    root = Path(__file__).resolve().parents[1]
    candidates = [root / 'runtime/python/Lib/site-packages/PyQt5/Qt5/plugins']
    try:
        import PyQt5
        candidates.append(Path(PyQt5.__file__).resolve().parent / 'Qt5/plugins')
    except ImportError:
        pass
    for plugins in candidates:
        if (plugins / 'platforms/qwindows.dll').is_file():
            QCoreApplication.setLibraryPaths([str(plugins)])
            return plugins
    return None


if __name__ == '__main__':
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    configure_qt()
    from chirp_upper_computer_v1_0 import main
    sys.exit(main())
