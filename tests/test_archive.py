import io, sqlite3, tempfile, unittest, zipfile
from pathlib import Path
from PIL import Image
from app import create_app, extract_metadata

def photo():
    image=Image.new('RGB',(600,400),'#728477'); exif=Image.Exif()
    exif[271]='FUJIFILM'; exif[272]='X-T5'
    exif[34665]={33434:1/250,33437:2.8,34855:400,37386:35.0,36867:'2026:11:13 10:30:00',42036:'XF35mmF1.4'}
    exif[34853]={1:'N',2:(22.0,18.0,0.0),3:'E',4:(114.0,10.0,0.0)}
    out=io.BytesIO(); image.save(out,'JPEG',exif=exif);out.seek(0);return out

class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.app=create_app(self.temp.name);self.client=self.app.test_client();self.headers={'X-Archive-Token':self.client.get('/api/session').json['token']}
    def tearDown(self): self.temp.cleanup()
    def album(self): return self.client.post('/api/albums',json={'title':'香港'},headers=self.headers).json['id']
    def test_metadata(self):
        m=extract_metadata(Image.open(photo()))
        for k,v in {'camera':'FUJIFILM X-T5','shutter':'1/250 s','aperture':'f/2.8','iso':'400','latitude':'22.300000','taken_at':'2026-11-13T10:30:00'}.items():self.assertEqual(m[k],v)
    def test_lifecycle_persistence_backup(self):
        aid=self.album();r=self.client.post(f'/api/albums/{aid}/photos',data={'photos':(photo(),'harbour.jpg')},headers=self.headers);self.assertEqual(r.status_code,201);pid=r.json['added'][0]
        self.client.patch(f'/api/photos/{pid}',json={'location':'中环','iso':'800'},headers=self.headers)
        self.assertEqual(self.client.post(f'/api/photos/{pid}/cover',headers=self.headers).status_code,200)
        self.assertEqual(create_app(self.temp.name).test_client().get('/api/albums').json[0]['photos'][0]['location'],'中环')
        response=self.client.get(f'/media/{pid}');self.assertEqual(response.status_code,200);response.close()
        response=self.client.get(f'/media/{pid}?original=1');self.assertIn('attachment',response.headers['Content-Disposition']);response.close()
        archive=zipfile.ZipFile(io.BytesIO(self.client.get('/api/backup').data));restored=sqlite3.connect(':memory:');restored.executescript(archive.read('archive.sql').decode());self.assertEqual(restored.execute('SELECT count(*) FROM photos').fetchone()[0],1)
        self.client.delete(f'/api/albums/{aid}',headers=self.headers);self.assertEqual(self.client.get('/api/albums').json,[]);self.assertEqual(list((Path(self.temp.name)/'originals').iterdir()),[])
    def test_invalid_file_and_protection(self):
        self.assertEqual(self.client.post('/api/albums',json={'title':'x'}).status_code,403)
        self.assertEqual(self.client.get('/api/albums',headers={'Host':'evil.example'}).status_code,403)
        aid=self.album();r=self.client.post(f'/api/albums/{aid}/photos',data={'photos':(io.BytesIO(b'bad'),'bad.jpg')},headers=self.headers);self.assertEqual(r.status_code,400);self.assertEqual(self.client.get('/api/albums').json[0]['photos'],[])
    def test_english_errors(self):
        headers={**self.headers, 'Accept-Language':'en'}
        response=self.client.post('/api/albums',json={'title':''},headers=headers)
        self.assertEqual(response.json['error'],'Please enter a collection title.')
        aid=self.album()
        response=self.client.post(f'/api/albums/{aid}/photos',data={'photos':(io.BytesIO(b'bad'),'bad.jpg')},headers=headers)
        self.assertIn('Cannot read this image',response.json['error'])
    def test_missing_exif(self):
        image=io.BytesIO();Image.new('RGB',(100,100),'white').save(image,'PNG');image.seek(0);aid=self.album();pid=self.client.post(f'/api/albums/{aid}/photos',data={'photos':(image,'plain.png')},headers=self.headers).json['added'][0]
        self.assertEqual(self.client.get('/api/albums').json[0]['photos'][0]['camera'],'');self.client.delete(f'/api/photos/{pid}',headers=self.headers);self.assertEqual(self.client.get(f'/media/{pid}').status_code,404)
if __name__=='__main__':unittest.main()
