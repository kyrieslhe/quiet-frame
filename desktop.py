"""Native desktop entry point. The loopback service is an internal UI transport."""
import os
import sqlite3
import subprocess
import sys
import threading
from pathlib import Path

import webview
from werkzeug.serving import make_server

from app import create_app


class DesktopBridge:
    def __init__(self, app):
        self._app = app
        self._window = None

    def choose_files(self, multiple=True):
        result = self._window.create_file_dialog(
            webview.OPEN_DIALOG, allow_multiple=bool(multiple),
            file_types=('Photographs (*.jpg;*.jpeg;*.png;*.webp;*.tif;*.tiff)',))
        return list(result or [])

    def choose_folder(self):
        result = self._window.create_file_dialog(webview.FOLDER_DIALOG)
        return list(result or [])

    def reveal_source(self, photo_id):
        with sqlite3.connect(self._app.extensions['archive']['db_path']) as conn:
            row = conn.execute('SELECT source_path FROM photos WHERE id=?', (photo_id,)).fetchone()
        if not row or not Path(row[0]).is_file():
            return {'ok': False}
        path = row[0]
        if sys.platform == 'darwin':
            subprocess.Popen(['open', '-R', path])
        elif sys.platform == 'win32':
            subprocess.Popen(['explorer', '/select,', os.path.normpath(path)])
        else:
            subprocess.Popen(['xdg-open', str(Path(path).parent)])
        return {'ok': True}

    def export_catalog(self):
        result = self._window.create_file_dialog(webview.SAVE_DIALOG, save_filename='quiet-frame-catalog.zip', file_types=('ZIP archive (*.zip)',))
        if not result:
            return {'cancelled': True}
        path = Path(result if isinstance(result, str) else result[0])
        with self._app.test_client() as client:
            response = client.get('/api/backup')
            try:
                path.write_bytes(response.data)
            finally:
                response.close()
        return {'ok': True, 'path': str(path)}

    def open_project(self):
        import webbrowser
        webbrowser.open('https://github.com/kyrieslhe/quiet-frame')
        return True


def main():
    app = create_app()
    lock = open(app.extensions['archive']['data'] / 'desktop.lock', 'a+')
    if os.name == 'posix':
        import fcntl
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            lock.seek(0)
            pid = lock.read().strip()
            if sys.platform == 'darwin' and pid.isdigit():
                import AppKit
                running = AppKit.NSRunningApplication.runningApplicationWithProcessIdentifier_(int(pid))
                if running:
                    running.activateWithOptions_(AppKit.NSApplicationActivateIgnoringOtherApps)
            lock.close()
            return
    lock.seek(0)
    lock.truncate()
    lock.write(str(os.getpid()))
    lock.flush()
    bridge = DesktopBridge(app)
    port = int(os.environ.get('PORT', '47321'))
    server = make_server('127.0.0.1', port, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    bridge._window = webview.create_window(
        '留影 · Quiet Frame', f'http://127.0.0.1:{port}', js_api=bridge,
        width=1440, height=920, min_size=(1000, 650),
        background_color='#f5f6f4', text_select=True)
    try:
        webview.start(private_mode=False, storage_path=str(app.extensions['archive']['data'] / 'window-state'))
    finally:
        server.shutdown()
        server.server_close()
        lock.close()


if __name__ == '__main__':
    main()
