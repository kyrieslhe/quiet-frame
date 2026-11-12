"""Quiet Frame — a private, local photographic archive."""
import io
import json
import os
import secrets
import sqlite3
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
    app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024
    default_data = ROOT / 'data'
    if getattr(__import__('sys'), 'frozen', False):
        if __import__('sys').platform == 'darwin':
            default_data = Path.home() / 'Library' / 'Application Support' / 'Quiet Frame'
        elif os.name == 'nt':
            default_data = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / 'AppData' / 'Local'))) / 'Quiet Frame'
        else:
            default_data = Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local' / 'share'))) / 'quiet-frame'
    data = Path(data_dir or os.environ.get('QUIET_FRAME_DATA', default_data)).resolve()
    for directory in (data, data / 'previews'):
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
        CREATE TABLE IF NOT EXISTS photos (id TEXT PRIMARY KEY, album_id TEXT NOT NULL REFERENCES albums(id) ON DELETE CASCADE, filename TEXT NOT NULL, original_name TEXT NOT NULL, metadata TEXT NOT NULL, position INTEGER NOT NULL, source_path TEXT NOT NULL DEFAULT '');''')
        columns = {row['name'] for row in conn.execute('PRAGMA table_info(photos)')}
        if 'source_path' not in columns:
            conn.execute("ALTER TABLE photos ADD COLUMN source_path TEXT NOT NULL DEFAULT ''")
        # Preserve existing imports as references to their old on-disk copies.
        # Neither migration nor record removal deletes these files.
        for row in conn.execute("SELECT id, filename FROM photos WHERE source_path='' "):
            conn.execute('UPDATE photos SET source_path=? WHERE id=?',
                         (str(data / 'originals' / row['filename']), row['id']))

    token = secrets.token_urlsafe(32)
    app.extensions['archive'] = dict(data=data, db_path=db_path)

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
        return jsonify(error=tr('路径列表过大，请分批添加。', 'Too many paths. Please add them in smaller batches.')), 413

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
        photos = []
        for row in conn.execute('SELECT * FROM photos WHERE album_id=? ORDER BY position, rowid', (album_id,)):
            preview = data / 'previews' / (row['id'] + '.jpg')
            try:
                exists = Path(row['source_path']).is_file()
            except OSError:
                exists = False
            photos.append(dict(id=row['id'], album_id=row['album_id'], original_name=row['original_name'],
                               position=row['position'], source_path=row['source_path'], source_exists=exists,
                               preview_version=preview.stat().st_mtime_ns if preview.exists() else 0,
                               **json.loads(row['metadata'])))
        return photos

    @app.get('/api/albums')
    def albums():
        with db() as conn:
            return jsonify([dict(dict(row), photos=photos_for(conn, row['id']))
                            for row in conn.execute('SELECT * FROM albums ORDER BY created_at DESC')])

    @app.post('/api/albums')
    def create_album():
        body = request.get_json()
        title = str(body.get('title', '')).strip()
        if not title:
            return jsonify(error=tr('请填写摄影集名称。', 'Please enter a collection title.')), 400
        album_id = uuid4().hex
        with db() as conn:
            conn.execute('INSERT INTO albums VALUES (?,?,?,?,?,?)',
                         (album_id, title[:200], str(body.get('description', ''))[:10000],
                          str(body.get('location', ''))[:500], str(body.get('date', ''))[:40], datetime.now().isoformat()))
        return jsonify(id=album_id), 201

    @app.patch('/api/albums/<album_id>')
    def edit_album(album_id):
        body = request.get_json()
        if not str(body.get('title', '')).strip():
            return jsonify(error=tr('请填写摄影集名称。', 'Please enter a collection title.')), 400
        with db() as conn:
            changed = conn.execute('UPDATE albums SET title=?, description=?, location=?, date=? WHERE id=?',
                                   tuple(str(body.get(key, ''))[:10000] for key in ('title', 'description', 'location', 'date')) + (album_id,)).rowcount
        if not changed:
            abort(404)
        return jsonify(ok=True)

    @app.delete('/api/albums/<album_id>')
    def delete_album(album_id):
        with db() as conn:
            files = list(conn.execute('SELECT id FROM photos WHERE album_id=?', (album_id,)))
            conn.execute('DELETE FROM albums WHERE id=?', (album_id,))
        for row in files:
            (data / 'previews' / (row['id'] + '.jpg')).unlink(missing_ok=True)
        return jsonify(ok=True)

    def read_photo(path, photo_id):
        preview = data / 'previews' / (photo_id + '.jpg')
        temporary = preview.with_suffix('.tmp')
        try:
            with Image.open(path) as image:
                if image.format not in ('JPEG', 'PNG', 'WEBP', 'TIFF'):
                    raise ValueError(tr('支持 JPG、PNG、WebP、TIFF；HEIC / RAW 请先导出为 JPG。',
                                        'Supported formats: JPG, PNG, WebP, TIFF. Export HEIC / RAW as JPG first.'))
                metadata = extract_metadata(image)
                metadata.update(title=path.stem, notes='')
                thumb = ImageOps.exif_transpose(image)
                thumb.thumbnail((2400, 2400))
                if thumb.mode in ('RGBA', 'LA'):
                    bg = Image.new('RGB', thumb.size, 'white')
                    bg.paste(thumb, mask=thumb.getchannel('A'))
                    thumb = bg
                thumb.convert('RGB').save(temporary, format='JPEG', quality=88)
                temporary.replace(preview)
            return metadata
        finally:
            temporary.unlink(missing_ok=True)

    def validated_path(value):
        if not isinstance(value, str) or not Path(value).expanduser().is_absolute():
            raise ValueError(tr('请使用完整的文件路径。', 'Please provide an absolute file path.'))
        path = Path(value).expanduser().resolve()
        if not path.is_file():
            raise ValueError(tr('原文件不存在或磁盘未连接。', 'The source file is missing or its drive is disconnected.'))
        return path

    @app.post('/api/folders/scan')
    def scan_folder():
        body = request.get_json()
        folder_value = body.get('path', '')
        if not isinstance(folder_value, str) or not Path(folder_value).expanduser().is_absolute():
            return jsonify(error=tr('请使用完整的文件夹路径。', 'Please provide an absolute folder path.')), 400
        folder = Path(folder_value).expanduser().resolve()
        if not folder.is_dir():
            return jsonify(error=tr('文件夹不存在或磁盘未连接。', 'Folder not found or drive disconnected.')), 400
        extensions = {'.jpg', '.jpeg', '.png', '.webp', '.tif', '.tiff'}
        try:
            paths = []
            for path in (folder.rglob('*') if body.get('recursive') else folder.iterdir()):
                if path.is_file() and path.suffix.lower() in extensions:
                    paths.append(str(path.resolve()))
                    if len(paths) > 10000:
                        return jsonify(error=tr('一次最多添加 10000 张，请选择更小的文件夹。', 'Select a smaller folder (up to 10,000 photographs).')), 400
            return jsonify(paths=sorted(paths), folder_name=folder.name)
        except OSError:
            return jsonify(error=tr('无法读取该文件夹，请检查权限。', 'Cannot read this folder. Please check permissions.')), 400

    @app.post('/api/albums/<album_id>/photos')
    def add_references(album_id):
        body = request.get_json(silent=True) or {}
        paths = body.get('paths')
        if not isinstance(paths, list) or not paths or len(paths) > 200:
            return jsonify(error=tr('请选择照片路径（每批最多 200 个）。', 'Select photograph paths (up to 200 per batch).')), 400
        with db() as conn:
            if not conn.execute('SELECT id FROM albums WHERE id=?', (album_id,)).fetchone():
                abort(404)
        added, skipped, errors = [], [], []
        for value in paths:
            photo_id = uuid4().hex
            try:
                path = validated_path(value)
                with db() as conn:
                    if conn.execute('SELECT id FROM photos WHERE album_id=? AND source_path=?', (album_id, str(path))).fetchone():
                        skipped.append(str(path))
                        continue
                metadata = read_photo(path, photo_id)
                with db() as conn:
                    position = conn.execute('SELECT COALESCE(MAX(position),-1)+1 FROM photos WHERE album_id=?', (album_id,)).fetchone()[0]
                    conn.execute('INSERT INTO photos (id,album_id,filename,original_name,metadata,position,source_path) VALUES (?,?,?,?,?,?,?)',
                                 (photo_id, album_id, '', path.name, json.dumps(metadata, ensure_ascii=False), position, str(path)))
                added.append(photo_id)
            except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
                (data / 'previews' / (photo_id + '.jpg')).unlink(missing_ok=True)
                error = tr('无法读取此图片，请检查文件格式。', 'Cannot read this image. Please check the file format.') if isinstance(exc, UnidentifiedImageError) else str(exc)
                errors.append(dict(filename=str(value), error=error))
        return jsonify(added=added, skipped=skipped, errors=errors)

    @app.post('/api/photos/<photo_id>/relink')
    def relink(photo_id):
        with db() as conn:
            if not conn.execute('SELECT id FROM photos WHERE id=?', (photo_id,)).fetchone():
                abort(404)
        try:
            path = validated_path(request.get_json().get('path'))
            read_photo(path, photo_id)
        except (OSError, ValueError, Image.DecompressionBombError) as exc:
            return jsonify(error=str(exc)), 400
        with db() as conn:
            conn.execute('UPDATE photos SET source_path=?, original_name=? WHERE id=?', (str(path), path.name, photo_id))
        return jsonify(ok=True)

    @app.patch('/api/photos/<photo_id>')
    def edit_photo(photo_id):
        body = request.get_json()
        with db() as conn:
            row = conn.execute('SELECT metadata FROM photos WHERE id=?', (photo_id,)).fetchone()
            if not row:
                abort(404)
            metadata = json.loads(row['metadata'])
            metadata.update({key: str(body[key])[:10000] for key in FIELDS if key in body})
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
            changed = conn.execute('DELETE FROM photos WHERE id=?', (photo_id,)).rowcount
        if not changed:
            abort(404)
        (data / 'previews' / (photo_id + '.jpg')).unlink(missing_ok=True)
        return jsonify(ok=True)

    @app.get('/media/<photo_id>')
    def media(photo_id):
        with db() as conn:
            row = conn.execute('SELECT * FROM photos WHERE id=?', (photo_id,)).fetchone()
        if not row:
            abort(404)
        if request.args.get('original') == '1':
            path = Path(row['source_path'])
            if not path.is_file():
                return jsonify(error=tr('原文件离线，请重新定位。', 'Source file offline. Please relink it.')), 404
            return send_file(path, as_attachment=True, download_name=row['original_name'])
        return send_file(data / 'previews' / (photo_id + '.jpg'), max_age=300)

    @app.get('/api/backup')
    def backup():
        snapshot = sqlite3.connect(':memory:')
        with db() as conn:
            conn.backup(snapshot)
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
            z.writestr('archive.sql', '\n'.join(snapshot.iterdump()))
            z.writestr('README.txt', 'Quiet Frame catalog backup. Contains source paths, metadata and previews. Original photographs are NOT included; back them up separately. Restore source drives at their original paths or relink files in the app.')
            for path in (data / 'previews').iterdir():
                if path.is_file() and path.suffix == '.jpg':
                    z.write(path, f'previews/{path.name}')
        snapshot.close()
        archive.seek(0)
        return send_file(archive, mimetype='application/zip', as_attachment=True, download_name='quiet-frame-catalog.zip')
    return app


if __name__ == '__main__':
    # Developer-only UI preview. Normal launches use the native desktop window.
    port = int(os.environ.get('PORT', '47321'))
    create_app().run(host='127.0.0.1', port=port, debug=False)
