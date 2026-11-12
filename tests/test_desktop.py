"""Bridge contracts; optional when only backend dependencies are installed."""
import tempfile
import unittest
import zipfile
from pathlib import Path
try:
    from desktop import DesktopBridge
except ImportError:
    DesktopBridge = None
from app import create_app


@unittest.skipIf(DesktopBridge is None, 'Desktop dependencies are optional in server CI')
class DesktopBridgeTests(unittest.TestCase):
    def test_native_picker_cancel_and_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            app = create_app(Path(directory) / 'data')
            bridge = DesktopBridge(app)
            class Window:
                result = None
                def create_file_dialog(self, *args, **kwargs):
                    return self.result
            bridge._window = Window()
            self.assertEqual(bridge.choose_files(), [])
            self.assertEqual(bridge.choose_folder(), [])
            self.assertTrue(bridge.export_catalog()['cancelled'])
            destination = Path(directory) / 'catalog.zip'
            bridge._window.result = [str(destination)]
            self.assertTrue(bridge.export_catalog()['ok'])
            with zipfile.ZipFile(destination) as archive:
                self.assertIn('archive.sql', archive.namelist())
                self.assertFalse(any(n.startswith('originals/') for n in archive.namelist()))
            # Only explicit methods may be exposed across the JS–Python bridge.
            self.assertFalse(hasattr(bridge, 'app'))
            self.assertFalse(hasattr(bridge, 'window'))
