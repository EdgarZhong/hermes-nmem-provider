"""Actual HTTP roundtrips against a disposable local server, not a real NM service."""
import importlib
import json
import sys
import threading
import types
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
pkg=types.ModuleType('_nm_http_test'); pkg.__path__=[str(ROOT)]; sys.modules[pkg.__name__]=pkg
C=importlib.import_module('_nm_http_test.personal_client')


class Handler(BaseHTTPRequestHandler):
    calls=[]
    def log_message(self,*args): pass
    def do_GET(self):
        self.calls.append((self.path,dict(self.headers)))
        if self.path=='/redirect':
            self.send_response(302); self.send_header('Location','http://127.0.0.1:1/never'); self.end_headers(); return
        if self.path=='/missing': self.send_response(404); self.end_headers(); return
        self.send_response(200); self.send_header('Content-Type','application/json'); self.end_headers()
        self.wfile.write(json.dumps({'rendered_markdown':'stable context'}).encode())
    def do_POST(self):
        value=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.calls.append((self.path,value)); self.send_response(200); self.end_headers(); self.wfile.write(b'{"success":true}')


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        cls.worker=threading.Thread(target=cls.server.serve_forever,daemon=True); cls.worker.start()
    @classmethod
    def tearDownClass(cls): cls.server.shutdown(); cls.server.server_close(); cls.worker.join()
    def setUp(self):
        Handler.calls=[]
        self.url=f'http://127.0.0.1:{self.server.server_port}'
        self.base=patch.object(C.PersonalMemClient,'_api_url',return_value=self.url); self.base.start()
        self.key=patch.object(C.PersonalMemClient,'_api_key',return_value='test-not-secret'); self.key.start()
    def tearDown(self): self.key.stop(); self.base.stop()
    def test_bundle_excludes_wm_and_preserves_space(self):
        client=C.PersonalMemClient(timeout=2,space='个人 空间')
        with patch.object(C.NowledgeMemClient,'_cli',return_value={'rendered_markdown':'stable context'}) as cli:
            self.assertEqual(client.context_bundle(host_agent_id='edgar-test')['rendered_markdown'],'stable context')
        self.assertEqual(cli.call_args.args[0],['context','read','--source-app','hermes','--no-working-memory',
                                              '--host-agent-id','edgar-test','--space-id','个人 空间'])
        self.assertEqual(Handler.calls,[])
    def test_credentials_headers_not_query(self):
        C.PersonalMemClient().request_json('GET','/context/bundle')
        path,headers=Handler.calls[0]
        self.assertNotIn('test-not-secret',path); self.assertEqual(headers.get('Authorization'),'Bearer test-not-secret')
    def test_redirect_is_not_followed(self):
        with self.assertRaises(C.MemHTTPError) as caught: C.PersonalMemClient().request_json('GET','/redirect')
        self.assertEqual(caught.exception.status,302); self.assertEqual(len(Handler.calls),1)
    def test_http_errors_do_not_echo_body(self):
        with self.assertRaises(C.MemHTTPError) as caught: C.PersonalMemClient().request_json('GET','/missing')
        self.assertEqual(str(caught.exception),'NM HTTP 404')
    def test_relative_path_required(self):
        with self.assertRaises(ValueError): C.PersonalMemClient().request_json('GET','//other.test/data')
    def test_upstream_append_transport_and_deduplicate(self):
        C.PersonalMemClient(space='default').append_thread('conv/1',[{'role':'user','content':'test'}])
        path,payload=Handler.calls[0]
        self.assertEqual(path,'/threads/conv%2F1/append'); self.assertTrue(payload['deduplicate'])
        self.assertEqual(payload['space_id'],'default')


if __name__=='__main__': unittest.main()
