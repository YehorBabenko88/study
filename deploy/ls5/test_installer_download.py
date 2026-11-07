import hashlib,io,json,tempfile,unittest,zipfile
from pathlib import Path
import resumable_download as d

class Response(io.BytesIO):
    def __init__(self,data,status=200,headers=None):super().__init__(data);self.status=status;self.headers=headers or {'Content-Length':str(len(data)),'ETag':'"v1"'}

class DownloadTests(unittest.TestCase):
    def artifact(self,data):return {'id':'fixture','url':'https://www.python.org/fixture.zip','size':len(data),'sha256':hashlib.sha256(data).hexdigest()}
    def test_partial_power_loss_resumes_with_matching_etag_and_range(self):
        data=b'abcdefgh';artifact=self.artifact(data);requests=[]
        class Interrupted(Response):
            def read(self,size=-1):
                if self.tell():raise OSError('power lost')
                return super().read(3)
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'artifact.zip'
            def first(request,timeout):return Interrupted(data)
            with self.assertRaises(OSError):d.download(artifact,target,{'www.python.org'},opener=first)
            self.assertEqual(target.with_name(target.name+'.part').read_bytes(),b'abc')
            def resume(request,timeout):
                requests.append(request)
                return Response(data[3:],206,{'ETag':'"v1"','Content-Range':'bytes 3-7/8','Content-Length':'5'})
            self.assertEqual(d.download(artifact,target,{'www.python.org'},opener=resume).read_bytes(),data)
            self.assertEqual(requests[0].get_header('Range'),'bytes=3-')
            self.assertEqual(requests[0].get_header('If-range'),'"v1"')
    def test_corrupt_download_quarantined_never_activated(self):
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'artifact.zip'
            with self.assertRaises(ValueError):d.download(self.artifact(b'good'),target,{'www.python.org'},opener=lambda *a,**k:Response(b'evil'))
            self.assertFalse(target.exists());self.assertTrue(list(Path(folder).glob('*.quarantine.*')))
    def test_untrusted_url_and_bad_range_rejected(self):
        artifact=self.artifact(b'abcdefgh')
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'artifact.zip'
            for url in ('http://www.python.org/a','https://evil.example/a','https://user@www.python.org/a'):
                bad=dict(artifact,url=url)
                with self.assertRaises(ValueError):d.download(bad,target,{'www.python.org'},opener=lambda *a: self.fail('network escaped'))
            target.with_name(target.name+'.part').write_bytes(b'abc')
            target.with_name(target.name+'.part.json').write_text(json.dumps(dict(artifact,etag='"v1"')))
            with self.assertRaises(ValueError):d.download(artifact,target,{'www.python.org'},opener=lambda *a,**k:Response(b'defgh',206,{'ETag':'"v2"','Content-Range':'bytes 3-7/8','Content-Length':'5'}))
            self.assertFalse(target.exists())
    def test_archive_traversal_links_and_bomb_refused(self):
        for kind in ('traversal','link','bomb'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as folder:
                source=Path(folder)/'archive.zip'
                with zipfile.ZipFile(source,'w',compression=zipfile.ZIP_DEFLATED) as archive:
                    if kind=='traversal':archive.writestr('../escape',b'x')
                    if kind=='link':
                        item=zipfile.ZipInfo('link');item.create_system=3;item.external_attr=(0o120777<<16);archive.writestr(item,'target')
                    if kind=='bomb':archive.writestr('large',b'0'*100000)
                with self.assertRaises(ValueError):d.extract_zip(source,Path(folder)/'out')
                self.assertFalse((Path(folder)/'escape').exists())
    def test_opt_in_redirects_preserve_only_safe_resume_headers_and_bound_hops(self):
        from urllib.request import Request
        handler=d.SafeRedirect({'www.python.org','cdn.example.test'},max_hops=2)
        request=Request('https://www.python.org/a',headers={'Range':'bytes=3-','If-Range':'"v1"','Authorization':'secret','Cookie':'private','Accept-Encoding':'identity'})
        next_request=handler.redirect_request(request,None,302,'redirect',{},'https://cdn.example.test/signed?Expires=1')
        self.assertEqual(next_request.get_header('Range'),'bytes=3-');self.assertEqual(next_request.get_header('If-range'),'"v1"')
        self.assertIsNone(next_request.get_header('Authorization'));self.assertIsNone(next_request.get_header('Cookie'))
        next_request=handler.redirect_request(next_request,None,302,'redirect',{},'https://cdn.example.test/b')
        with self.assertRaises(ValueError):handler.redirect_request(next_request,None,302,'redirect',{},'https://cdn.example.test/c')
        for url in ('http://cdn.example.test/a','https://evil.example/a','https://cdn.example.test:444/a','https://user:pass@cdn.example.test/a'):
            with self.subTest(url=url),self.assertRaises(ValueError):handler.redirect_request(request,None,302,'redirect',{},url)
