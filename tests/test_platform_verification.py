"""Real-source release checks; explicit mutations/fake S3 test failures only."""
import io
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from botocore.response import StreamingBody
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.marine_data.platform.pipeline import run, digest
from backend.marine_data.platform.verify import audit_release, verify_s3_file
from scripts.operations.verify_objective2 import check_api

FIXTURE = Path(__file__).parent / 'fixtures/ibtracs_real_excerpt.csv'


def publish(root):
    return run('ibtracs', FIXTURE, root=root, source_url='https://www.ncei.noaa.gov/',
               coverage='Retained NOAA excerpt only')


def test_full_audit_and_api_handoff(tmp_path, monkeypatch):
    monkeypatch.setenv('MARINEVERSE_DATA_DIR', str(tmp_path))
    report = publish(tmp_path)
    audit = audit_release(tmp_path, 'ibtracs')
    assert audit['verified']
    assert audit['accepted'] == report['accepted']
    assert check_api(TestClient(app), '', audit)['verified']


@pytest.mark.parametrize('target', ['bronze', 'silver', 'objective1', 'objective3', 'objective4'])
def test_each_corrupt_file_fails(tmp_path, target):
    report = publish(tmp_path)
    if target == 'bronze':
        path = next((tmp_path / 'bronze/ibtracs').glob('*/*.csv'))
    elif target == 'silver':
        path = tmp_path / 'silver/ibtracs' / report['release'] / 'records.jsonl'
    else:
        path = tmp_path / report['products'][target]['path']
    path.write_text('corrupt')
    assert not audit_release(tmp_path, 'ibtracs')['verified']


@pytest.mark.parametrize('mutation', ['count', 'lineage', 'path', 'status', 'dataset', 'null', 'quality'])
def test_receipt_and_lineage_fail_closed(tmp_path, monkeypatch, mutation):
    monkeypatch.setenv('MARINEVERSE_DATA_DIR', str(tmp_path))
    report = publish(tmp_path)
    if mutation == 'count':
        report['products']['objective1']['records'] += 1
    elif mutation == 'lineage':
        path = tmp_path / report['products']['objective3']['path']
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        rows[0]['provenance']['release'] = 'other'
        path.write_text(''.join(json.dumps(row) + '\n' for row in rows))
        report['products']['objective3']['sha256'] = digest(path)
    elif mutation == 'path':
        report['products']['objective1']['path'] = report['products']['objective3']['path']
    elif mutation == 'null':
        report = None
    elif mutation == 'quality':
        report['read'] += 1
    else:
        report[mutation] = 'wrong'
    (tmp_path / 'catalog/ibtracs/current.json').write_text(json.dumps(report))
    assert not audit_release(tmp_path, 'ibtracs')['verified']
    if mutation in {'path', 'status', 'dataset', 'null'}:
        client = TestClient(app)
        assert client.get('/api/v1/products/ibtracs/objective1').status_code == 503
        assert client.get('/api/v1/products').status_code == 503


def test_symlink_escape(tmp_path):
    report = publish(tmp_path)
    path = tmp_path / report['products']['objective1']['path']
    outside = tmp_path / 'private.jsonl'
    outside.write_bytes(path.read_bytes())
    path.unlink()
    path.symlink_to(outside)
    assert not audit_release(tmp_path, 'ibtracs')['verified']


@pytest.mark.parametrize('remote', [b'1234', b'xxxx', b'123'])
def test_s3_full_bytes_not_etag(tmp_path, remote):
    path = tmp_path / 'source'
    path.write_bytes(b'1234')
    stream = io.BytesIO(remote)
    client = Mock()
    client.get_object.return_value = {'Body': StreamingBody(stream, len(remote)),
                                      'ContentLength': len(remote), 'ETag': 'not-a-content-hash-2'}
    result = verify_s3_file(path, 'private-bucket', 'private-key', client)
    assert result['verified'] is (remote == b'1234')
    assert stream.closed
    assert 'private' not in json.dumps(result)
    client.get_object.assert_called_once_with(Bucket='private-bucket', Key='private-key')


def test_s3_closes_on_read_failure(tmp_path):
    path = tmp_path / 'source'
    path.write_bytes(b'1234')
    body = Mock()
    body.iter_chunks.side_effect = OSError('interrupted')
    client = Mock()
    client.get_object.return_value = {'Body': body, 'ContentLength': 4}
    with pytest.raises(OSError):
        verify_s3_file(path, 'bucket', 'key', client)
    body.close.assert_called_once()


def test_empty_or_changed_release_is_not_api_verified(tmp_path, monkeypatch):
    monkeypatch.setenv("MARINEVERSE_DATA_DIR", str(tmp_path))
    assert not audit_release(tmp_path, 'ibtracs')['verified']
    report = publish(tmp_path)
    audit = audit_release(tmp_path, 'ibtracs')
    publish(tmp_path)
    client = TestClient(app)
    assert not check_api(client, '', audit)['verified']


def test_identity_check_rejects_similar_user_and_malformed_response(monkeypatch):
    from subprocess import CompletedProcess
    from scripts.operations.objective2_readiness import check_aws
    for arn in ('arn:aws:iam::000000000000:user/marineverse-data-engineer-other', None, 42):
        monkeypatch.setattr('scripts.operations.objective2_readiness.subprocess.run',
                            lambda *a, **kw: CompletedProcess([], 0, json.dumps({'Arn': arn}), ''))
        assert not check_aws('marineverse', 'ap-south-1')['ready']
