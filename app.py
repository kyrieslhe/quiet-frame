"""Quiet Frame — a private, local photographic archive."""
import io
import json
import os
import secrets
import sqlite3
import threading
import webbrowser
import zipfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from flask import Flask, jsonify, request, send_file, send_from_directory, abort
from PIL import Image, ImageOps, UnidentifiedImageError

ROOT = Path(__file__).resolve().parent
FIELDS = ('title', 'location', 'taken_at', 'camera', 'lens', 'focal_length', 'aperture', 'shutter', 'iso', 'latitude', 'longitude', 'notes')


def extract_metadata(image):
    exif = image.getexif()
    tags = dict(exif)
    try:
        tags.update(exif.get_ifd(34665))
    except (KeyError, TypeError, ValueError):
        pass
    def value(key):
        v = tags.get(key, '')
        return str(v).strip('\x00 ').strip() if v is not None else ''
    def number(key, suffix='', prefix=''):
        try:
            return f'{prefix}{float(tags[key]):g}{suffix}'
        except (KeyError, TypeError, ValueError, ZeroDivisionError):
            return ''
    camera = ' '.join(dict.fromkeys(v for v in (value(271), value(272)) if v))
    shutter = ''
    try:
        seconds = float(tags[33434])
        shutter = f'1/{round(1 / seconds)} s' if 0 < seconds < 1 else f'{seconds:g} s'
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        pass
    date = value(36867) or value(306)
    if len(date) >= 19:
        date = date[:10].replace(':', '-') + 'T' + date[11:19]
    result = dict(camera=camera, lens=value(42036), focal_length=number(37386, ' mm'), aperture=number(33437, prefix='f/'), shutter=shutter, iso=value(34855), taken_at=date, latitude='', longitude='', location='')
    try:
        gps = exif.get_ifd(34853)
        def degrees(values):
            return float(values[0]) + float(values[1]) / 60 + float(values[2]) / 3600
        lat = degrees(gps[2]) * (-1 if gps.get(1) in ('S', b'S') else 1)
        lon = degrees(gps[4]) * (-1 if gps.get(3) in ('W', b'W') else 1)
        result.update(latitude=f'{lat:.6f}', longitude=f'{lon:.6f}', location=f'{lat:.5f}, {lon:.5f}')
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        pass
    return result


def create_app(data_dir=None):
    app = Flask(__name__, static_folder=str(ROOT / 'static'))
    app.config['MAX_CONTENT_LENGTH'] = 512 * 1024 * 1024
    data = Path(data_dir or os.environ.get('QUIET_FRAME_DATA', ROOT / 'data')).resolve()
    for directory in (data, data / 'originals', data / 'previews'):
        directory.mkdir(parents=True, exist_ok=True)
    db_path = data / 'archive.sqlite3'
    @contextmanager
    def db():
        conn = sqlite3.connect(db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys=ON')
        try:
            with conn:
                yield conn
        finally:
            conn.close()
    with db() as conn:
        conn.executescript('''CREATE TABLE IF NOT EXISTS albums (id TEXT PRIMARY KEY, title TEXT NOT NULL, description TEXT DEFAULT '', location TEXT DEFAULT '', date TEXT DEFAULT '', created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS photos (id TEXT PRIMARY KEY, album_id TEXT NOT NULL REFERENCES albums(id) ON DELETE CASCADE, filename TEXT NOT NULL, original_name TEXT NOT NULL, metadata TEXT NOT NULL, position INTEGER NOT NULL);''')
    token = secrets.token_urlsafe(32)
    def tr(zh, en):
        return en if request.headers.get('Accept-Language', '').startswith('en') else zh

    @app.before_request
    def local_only():
        if request.host.split(':')[0] not in ('127.0.0.1', 'localhost', '[::1]'):
            abort(403)
        if request.method in ('POST', 'PATCH', 'DELETE') and request.headers.get('X-Archive-Token') != token:
            abort(403)
    @app.errorhandler(413)
    def too_large(_):
        return jsonify(error=tr('一次导入总量请控制在 512 MB 以内。', 'Please keep each import below 512 MB.')), 413
    @app.errorhandler(400)
    def bad_request(_):
        return jsonify(error=tr('请求格式不正确。', 'Invalid request format.')), 400
    @app.get('/')
    def index():
        return send_from_directory(app.static_folder, 'index.html')
    @app.get('/api/session')
    def session():
        return jsonify(token=token)
    def photos_for(conn, album_id):
        return [dict(id=r['id'], album_id=r['album_id'], original_name=r['original_name'], position=r['position'], **json.loads(r['metadata'])) for r in conn.execute('SELECT * FROM photos WHERE album_id=? ORDER BY position, rowid', (album_id,))]
    @app.get('/api/albums')
    def albums():
        with db() as conn:
            return jsonify([dict(dict(r), photos=photos_for(conn, r['id'])) for r in conn.execute('SELECT * FROM albums ORDER BY created_at DESC')])
    @app.post('/api/albums')
    def create_album():
        body = request.get_json()
        title = str(body.get('title', '')).strip()
        if not title:
            return jsonify(error=tr('请填写摄影集名称。', 'Please enter a collection title.')), 400
        album_id = uuid4().hex
        with db() as conn:
            conn.execute('INSERT INTO albums VALUES (?,?,?,?,?,?)', (album_id, title[:200], str(body.get('description', ''))[:10000], str(body.get('location', ''))[:500], str(body.get('date', ''))[:40], datetime.now().isoformat()))
        return jsonify(id=album_id), 201
    @app.patch('/api/albums/<album_id>')
    def edit_album(album_id):
        body = request.get_json()
        if not str(body.get('title', '')).strip():
            return jsonify(error=tr('请填写摄影集名称。', 'Please enter a collection title.')), 400
        with db() as conn:
            changed = conn.execute('UPDATE albums SET title=?, description=?, location=?, date=? WHERE id=?', tuple(str(body.get(k, ''))[:10000] for k in ('title', 'description', 'location', 'date')) + (album_id,)).rowcount
        if not changed:
            abort(404)
        return jsonify(ok=True)
    @app.delete('/api/albums/<album_id>')
    def delete_album(album_id):
        with db() as conn:
            files = list(conn.execute('SELECT id, filename FROM photos WHERE album_id=?', (album_id,)))
            conn.execute('DELETE FROM albums WHERE id=?', (album_id,))
        for row in files:
            (data / 'originals' / row['filename']).unlink(missing_ok=True)
            (data / 'previews' / (row['id'] + '.jpg')).unlink(missing_ok=True)
        return jsonify(ok=True)
    @app.post('/api/albums/<album_id>/photos')
    def upload(album_id):
        with db() as conn:
            if not conn.execute('SELECT id FROM albums WHERE id=?', (album_id,)).fetchone():
                abort(404)
        added, errors = [], []
        for file in request.files.getlist('photos'):
            photo_id = uuid4().hex
            original = None
            preview = data / 'previews' / (photo_id + '.jpg')
            try:
                image = Image.open(file.stream)
                if image.format not in ('JPEG', 'PNG', 'WEBP', 'TIFF'):
                    raise ValueError(tr('支持 JPG、PNG、WebP、TIFF；HEIC / RAW 请先导出为 JPG。', 'Supported formats: JPG, PNG, WebP, TIFF. Export HEIC / RAW as JPG first.'))
                metadata = extract_metadata(image)
                metadata.update(title=Path(file.filename or '未命名').stem, notes='')
                thumb = ImageOps.exif_transpose(image)
                thumb.thumbnail((2400, 2400))
                if thumb.mode in ('RGBA', 'LA'):
                    bg = Image.new('RGB', thumb.size, 'white')
                    bg.paste(thumb, mask=thumb.getchannel('A'))
                    thumb = bg
                thumb.convert('RGB').save(preview, quality=90)
                ext = {'JPEG': '.jpg', 'PNG': '.png', 'WEBP': '.webp', 'TIFF': '.tiff'}[image.format]
                filename = photo_id + ext
                original = data / 'originals' / filename
                file.stream.seek(0)
                file.save(original)
                with db() as conn:
                    position = conn.execute('SELECT COALESCE(MAX(position),-1)+1 FROM photos WHERE album_id=?', (album_id,)).fetchone()[0]
                    conn.execute('INSERT INTO photos VALUES (?,?,?,?,?,?)', (photo_id, album_id, filename, Path(file.filename or 'photo').name, json.dumps(metadata, ensure_ascii=False), position))
                added.append(photo_id)
            except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
                preview.unlink(missing_ok=True)
                if original:
                    original.unlink(missing_ok=True)
                errors.append(dict(filename=file.filename, error=tr('无法读取此图片，请检查文件格式。', 'Cannot read this image. Please check the file format.') if isinstance(exc, UnidentifiedImageError) else str(exc) or tr('无法读取此图片', 'Cannot read this image')))
        return jsonify(added=added, errors=errors, error='；'.join(f"{e['filename']}：{e['error']}" for e in errors) if not added else ''), 201 if added else 400
    @app.patch('/api/photos/<photo_id>')
    def edit_photo(photo_id):
        body = request.get_json()
        with db() as conn:
            row = conn.execute('SELECT * FROM photos WHERE id=?', (photo_id,)).fetchone()
            if not row:
                abort(404)
            metadata = json.loads(row['metadata'])
            metadata.update({k: str(body[k])[:10000] for k in FIELDS if k in body})
            conn.execute('UPDATE photos SET metadata=? WHERE id=?', (json.dumps(metadata, ensure_ascii=False), photo_id))
        return jsonify(ok=True)
    @app.post('/api/photos/<photo_id>/cover')
    def cover(photo_id):
        with db() as conn:
            row = conn.execute('SELECT album_id FROM photos WHERE id=?', (photo_id,)).fetchone()
            if not row:
                abort(404)
            position = conn.execute('SELECT MIN(position)-1 FROM photos WHERE album_id=?', (row['album_id'],)).fetchone()[0]
            conn.execute('UPDATE photos SET position=? WHERE id=?', (position, photo_id))
        return jsonify(ok=True)
    @app.delete('/api/photos/<photo_id>')
    def delete_photo(photo_id):
        with db() as conn:
            row = conn.execute('SELECT filename FROM photos WHERE id=?', (photo_id,)).fetchone()
            if not row:
                abort(404)
            conn.execute('DELETE FROM photos WHERE id=?', (photo_id,))
        (data / 'originals' / row['filename']).unlink(missing_ok=True)
        (data / 'previews' / (photo_id + '.jpg')).unlink(missing_ok=True)
        return jsonify(ok=True)
    @app.get('/media/<photo_id>')
    def media(photo_id):
        with db() as conn:
            row = conn.execute('SELECT * FROM photos WHERE id=?', (photo_id,)).fetchone()
        if not row:
            abort(404)
        if request.args.get('original') == '1':
            return send_file(data / 'originals' / row['filename'], as_attachment=True, download_name=row['original_name'])
        return send_file(data / 'previews' / (photo_id + '.jpg'), max_age=86400)
    @app.get('/api/backup')
    def backup():
        # SQLite's backup API gives a consistent snapshot, including during imports.
        snapshot = sqlite3.connect(':memory:')
        with db() as conn:
            conn.backup(snapshot)
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
            z.writestr('archive.sql', '\n'.join(snapshot.iterdump()))
            for directory in ('originals', 'previews'):
                for path in (data / directory).iterdir():
                    if path.is_file():
                        z.write(path, f'{directory}/{path.name}')
        snapshot.close()
        archive.seek(0)
        return send_file(archive, mimetype='application/zip', as_attachment=True, download_name='quiet-frame-backup.zip')
    return app


if __name__ == '__main__':
    port = int(os.environ.get('PORT', '47321'))
    app = create_app()
    url = f'http://127.0.0.1:{port}'
    print(f'\n  Quiet Frame · 留影\n  {url}\n  按 Ctrl+C 停止。\n', flush=True)
    if '--no-browser' not in __import__('sys').argv:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    app.run(host='127.0.0.1', port=port, debug=False)
