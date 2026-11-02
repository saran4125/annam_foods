import base64
import json
import os
from pathlib import Path
from unittest.mock import patch
import pytest
from apps.operations.backups import create_backup,verify_backup


@pytest.fixture
def backup_setup(settings,tmp_path,monkeypatch):
    settings.MEDIA_ROOT=tmp_path/'media';settings.PRIVATE_BILLS_ROOT=tmp_path/'bills';settings.STATIC_ROOT=tmp_path/'static'
    settings.MEDIA_ROOT.mkdir();settings.PRIVATE_BILLS_ROOT.mkdir()
    (settings.MEDIA_ROOT/'photo.jpg').write_bytes(b'local-photo')
    (settings.PRIVATE_BILLS_ROOT/'invoice.pdf').write_bytes(b'private-bill')
    outside=tmp_path/'do-not-copy.txt';outside.write_text('private unrelated file')
    (settings.MEDIA_ROOT/'symlink.jpg').symlink_to(outside)
    settings.SECRET_KEY='synthetic-signing-key';settings.SECRETS_KEY='synthetic-encryption-key'
    monkeypatch.setenv('BACKUP_ENCRYPTION_KEY',base64.urlsafe_b64encode(os.urandom(32)).decode())
    def dump(args,**kwargs):Path(args[-1]).write_bytes(b'PGDMP-synthetic-database')
    return tmp_path,patch('apps.operations.backups.subprocess.run',side_effect=dump)


def test_encrypted_backup_recovers_media_bills_keys_and_database_without_copying_links(backup_setup):
    root,dump=backup_setup;backup=root/'backups'/'snapshot.enc'
    with dump:result=create_backup(backup)
    assert result['files']==4 and backup.stat().st_mode&0o777==0o600
    assert b'private-bill' not in backup.read_bytes() and b'synthetic-signing-key' not in backup.read_bytes()
    recovered=root/'recovery';report=verify_backup(backup,recovered)
    assert report['files']==4
    assert (recovered/'public-media/photo.jpg').read_bytes()==b'local-photo'
    assert (recovered/'private-bills/invoice.pdf').read_bytes()==b'private-bill'
    assert not (recovered/'public-media/symlink.jpg').exists()
    assert json.loads((recovered/'meta/recovery.json').read_text())['SECRETS_KEY']=='synthetic-encryption-key'
    assert (recovered/'meta/database.dump').read_bytes().startswith(b'PGDMP')


def test_changed_or_wrong_key_backup_never_extracts_unverified_data(backup_setup,monkeypatch):
    root,dump=backup_setup;backup=root/'snapshot.enc'
    with dump:create_backup(backup)
    contents=bytearray(backup.read_bytes());contents[-1]^=1;backup.write_bytes(contents)
    with pytest.raises(ValueError,match='authentication failed'):verify_backup(backup,root/'recovery')
    assert not (root/'recovery').exists()
    assert not list(root.glob('.backup-*'))


def test_backups_and_recovery_cannot_be_written_under_public_storage_or_overwritten(backup_setup):
    root,dump=backup_setup
    with pytest.raises(ValueError,match='outside public'):create_backup(root/'media'/'unsafe.enc')
    backup=root/'safe.enc'
    with dump:create_backup(backup)
    with pytest.raises(ValueError,match='never overwritten'):create_backup(backup)
    with pytest.raises(ValueError,match='outside public'):verify_backup(backup,root/'static'/'recovery')


def test_offsite_upload_streams_only_verified_encrypted_data_without_returning_token(backup_setup,monkeypatch):
    from unittest.mock import MagicMock
    from apps.operations.backups import upload_supabase_backup
    root,dump=backup_setup;backup=root/'offsite.enc'
    with dump:create_backup(backup)
    monkeypatch.setenv('BACKUP_SUPABASE_URL','https://project.example.test')
    monkeypatch.setenv('BACKUP_SUPABASE_BUCKET','private-backups')
    monkeypatch.setenv('BACKUP_SUPABASE_TOKEN','synthetic-private-token')
    connection=MagicMock();connection.getresponse.return_value.status=200
    with patch('http.client.HTTPSConnection',return_value=connection):result=upload_supabase_backup(backup)
    assert result=={'upload_confirmed':True,'object':'offsite.enc'}
    assert b''.join(call.args[0] for call in connection.send.call_args_list)==backup.read_bytes()
    assert 'synthetic-private-token' not in str(result)
    connection.putheader.assert_any_call('x-upsert','false')
    connection.close.assert_called_once()
