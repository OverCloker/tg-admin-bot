import json

from app import build_info


def test_revision_from_loose_and_packed_refs(tmp_path):
    git = tmp_path / '.git'
    (git / 'refs' / 'heads').mkdir(parents=True)
    (git / 'HEAD').write_text('ref: refs/heads/main\n')
    revision = 'a' * 40
    ref = git / 'refs' / 'heads' / 'main'
    ref.write_text(revision)
    assert build_info.git_revision(tmp_path) == revision
    ref.unlink()
    (git / 'packed-refs').write_text(f'# pack-refs\n{revision} refs/heads/main\n')
    assert build_info.git_revision(tmp_path) == revision


def test_detached_and_missing_checkout(tmp_path):
    assert build_info.git_revision(tmp_path) is None
    git = tmp_path / '.git'
    git.mkdir()
    (git / 'HEAD').write_text('b' * 40)
    assert build_info.git_revision(tmp_path) == 'b' * 40
    (git / 'HEAD').write_text('ref: ../../secret')
    assert build_info.git_revision(tmp_path) is None


def test_running_image_uses_stamp_not_new_checkout(tmp_path, monkeypatch):
    app = tmp_path / 'app'
    app.mkdir()
    git = tmp_path / '.git'
    git.mkdir()
    (git / 'HEAD').write_text('b' * 40)
    (app / 'build-info.json').write_text(json.dumps({'revision': 'a' * 40, 'builtAt': '2026-09-06T01:00:00+00:00'}))
    monkeypatch.setattr(build_info, '__file__', str(app / 'build_info.py'))
    build_info.get_build_info.cache_clear()
    try:
        data = build_info.get_build_info()
        assert data['shortRevision'] == 'aaaaaaa'
        assert data['source'] == 'image'
        assert data['builtAt'] == '2026-09-06T01:00:00+00:00'
        assert data['startedAt']
    finally:
        build_info.get_build_info.cache_clear()


def test_local_unknown_is_not_presented_as_a_release(tmp_path, monkeypatch):
    monkeypatch.setattr(build_info, '__file__', str(tmp_path / 'app' / 'build_info.py'))
    build_info.get_build_info.cache_clear()
    try:
        data = build_info.get_build_info()
        assert data['revision'] is None
        assert data['source'] == 'local'
        assert data['builtAt'] is None
    finally:
        build_info.get_build_info.cache_clear()
