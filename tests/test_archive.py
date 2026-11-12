import io
import json
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path

from PIL import Image
from app import create_app, extract_metadata


def photo():
    image = Image.new('RGB', (600, 400), '#728477')
    exif = Image.Exif()
    exif[271] = 'FUJIFILM'
    exif[272] = 'X-T5'
    exif[34665] = {33434: 1/250, 33437: 2.8, 34855: 400, 37386: 35.0,
                   36867: '2026:11:13 10:30:00', 42036: 'XF35mmF1.4'}
    exif[34853] = {1: 'N', 2: (22.0, 18.0, 0.0), 3: 'E', 4: (114.0, 10.0, 0.0)}
    output = io.BytesIO()
    image.save(output, 'JPEG', exif=exif)
    output.seek(0)
    return output


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.data = self.root / 'catalog'
        self.source = self.root / 'photos' / 'harbour.jpg'
        self.source.parent.mkdir()
        self.original_bytes = photo().read()
        self.source.write_bytes(self.original_bytes)
        self.app = create_app(self.data)
        self.client = self.app.test_client()
        self.headers = {'X-Archive-Token': self.client.get('/api/session').json['token']}

    def tearDown(self):
        self.temp.cleanup()

    def album(self):
        return self.client.post('/api/albums', json={'title': '香港'}, headers=self.headers).json['id']

    def add(self, aid=None, paths=None):
        return self.client.post(f'/api/albums/{aid or self.album()}/photos',
                                json={'paths': paths or [str(self.source)]}, headers=self.headers)

    def test_exif_gps(self):
        metadata = extract_metadata(Image.open(photo()))
        for key, value in {'camera': 'FUJIFILM X-T5', 'shutter': '1/250 s', 'aperture': 'f/2.8',
                           'iso': '400', 'latitude': '22.300000', 'taken_at': '2026-11-13T10:30:00'}.items():
            self.assertEqual(metadata[key], value)

    def test_reference_no_original_copy_and_removal_preserves_source(self):
        aid = self.album()
        pid = self.add(aid).json['added'][0]
        self.assertFalse((self.data / 'originals').exists())
        row = self.client.get('/api/albums').json[0]['photos'][0]
        self.assertEqual(row['source_path'], str(self.source.resolve()))
        self.assertTrue(row['source_exists'])
        self.client.patch(f'/api/photos/{pid}', json={'location': '中环'}, headers=self.headers)
        restarted = create_app(self.data).test_client()
        self.assertEqual(restarted.get('/api/albums').json[0]['photos'][0]['location'], '中环')
        response = self.client.get(f'/media/{pid}?original=1')
        self.assertEqual(response.data, self.original_bytes)
        response.close()
        self.client.delete(f'/api/photos/{pid}', headers=self.headers)
        self.assertEqual(self.source.read_bytes(), self.original_bytes)
        self.assertFalse((self.data / 'previews' / (pid + '.jpg')).exists())
        self.add(aid)
        self.client.delete(f'/api/albums/{aid}', headers=self.headers)
        self.assertEqual(self.source.read_bytes(), self.original_bytes)

    def test_missing_and_relink_preserves_edited_metadata(self):
        pid = self.add().json['added'][0]
        self.client.patch(f'/api/photos/{pid}', json={'location': '自定义地点', 'iso': '800'}, headers=self.headers)
        moved = self.source.with_name('moved.jpg')
        self.source.rename(moved)
        self.assertFalse(self.client.get('/api/albums').json[0]['photos'][0]['source_exists'])
        preview = self.client.get(f'/media/{pid}')
        self.assertEqual(preview.status_code, 200)
        preview.close()
        self.assertEqual(self.client.get(f'/media/{pid}?original=1').status_code, 404)
        response = self.client.post(f'/api/photos/{pid}/relink', json={'path': str(moved)}, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        record = self.client.get('/api/albums').json[0]['photos'][0]
        self.assertTrue(record['source_exists'])
        self.assertEqual(record['location'], '自定义地点')
        self.assertEqual(record['iso'], '800')
        self.assertEqual(moved.read_bytes(), self.original_bytes)

    def test_duplicate_folder_scan_and_backup_excludes_originals(self):
        aid = self.album()
        self.add(aid)
        self.assertEqual(len(self.add(aid).json['skipped']), 1)
        child = self.source.parent / 'child'
        child.mkdir()
        (child / 'nested.jpg').write_bytes(self.original_bytes)
        scan = self.client.post('/api/folders/scan', json={'path': str(self.source.parent), 'recursive': False}, headers=self.headers)
        self.assertEqual(len(scan.json['paths']), 1)
        scan = self.client.post('/api/folders/scan', json={'path': str(self.source.parent), 'recursive': True}, headers=self.headers)
        self.assertEqual(len(scan.json['paths']), 2)
        backup = zipfile.ZipFile(io.BytesIO(self.client.get('/api/backup').data))
        self.assertFalse(any(name.startswith('originals/') for name in backup.namelist()))
        restored = sqlite3.connect(':memory:')
        restored.executescript(backup.read('archive.sql').decode())
        self.assertEqual(restored.execute('SELECT source_path FROM photos').fetchone()[0], str(self.source.resolve()))
        restored.close()

    def test_validation_and_local_protection(self):
        self.assertEqual(self.client.post('/api/albums', json={'title': 'x'}).status_code, 403)
        self.assertEqual(self.client.get('/api/albums', headers={'Host': 'evil.example'}).status_code, 403)
        aid = self.album()
        response = self.add(aid, ['relative.jpg', str(self.root / 'missing.jpg')])
        self.assertEqual(len(response.json['errors']), 2)
        self.assertEqual(response.json['added'], [])
        self.assertEqual(self.client.post(f'/api/albums/{aid}/photos', data={'photos': (photo(), 'old-upload.jpg')}, headers=self.headers).status_code, 400)
        headers = {**self.headers, 'Accept-Language': 'en'}
        response = self.client.post('/api/albums', json={'title': ''}, headers=headers)
        self.assertEqual(response.json['error'], 'Please enter a collection title.')

    def test_legacy_migration_keeps_files(self):
        old_data = self.root / 'legacy'
        (old_data / 'originals').mkdir(parents=True)
        original = old_data / 'originals' / 'old.jpg'
        original.write_bytes(self.original_bytes)
        with sqlite3.connect(old_data / 'archive.sqlite3') as conn:
            conn.executescript('''CREATE TABLE albums (id TEXT PRIMARY KEY,title TEXT,description TEXT,location TEXT,date TEXT,created_at TEXT);
            CREATE TABLE photos (id TEXT PRIMARY KEY,album_id TEXT,filename TEXT,original_name TEXT,metadata TEXT,position INTEGER);
            INSERT INTO albums VALUES ('a','Old','','','','2026');''')
            conn.execute('INSERT INTO photos VALUES (?,?,?,?,?,?)', ('p', 'a', 'old.jpg', 'old.jpg', json.dumps({'title': 'Legacy'}), 0))
        app = create_app(old_data)
        client = app.test_client()
        record = client.get('/api/albums').json[0]['photos'][0]
        self.assertEqual(record['source_path'], str(original.resolve()))
        token = client.get('/api/session').json['token']
        client.delete('/api/albums/a', headers={'X-Archive-Token': token})
        self.assertEqual(original.read_bytes(), self.original_bytes)


if __name__ == '__main__':
    unittest.main()
