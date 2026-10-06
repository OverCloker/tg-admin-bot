import json
import struct
from pathlib import Path

import pytest


def test_cat_asset_allowlist_and_mime_types():
    from app.admin_api import admin_theme_asset, HTTPException
    for filename, mime in [('owner-cat-v4.glb', 'model/gltf-binary'),
                           ('cat-companion.bundle.js', 'text/javascript')]:
        response = admin_theme_asset(filename)
        assert response.headers['content-type'].startswith(mime)
        assert response.headers['x-content-type-options'] == 'nosniff'
        assert Path(response.path).is_file()
    for filename in ['cat-companion.js', 'cat-motion.mjs', '../.env', 'other.glb']:
        with pytest.raises(HTTPException) as error:
            admin_theme_asset(filename)
        assert error.value.status_code == 404


def test_shipped_cat_has_skin_and_animation_and_no_external_urls():
    model = Path(__file__).resolve().parents[1] / 'app/assets/themes/owner-cat-v4.glb'
    data = model.read_bytes()
    assert data[:4] == b'glTF'
    size, chunk_type = struct.unpack_from('<II', data, 12)
    assert chunk_type == 0x4E4F534A
    gltf = json.loads(data[20:20+size])
    assert len(gltf['skins'][0]['joints']) == 43
    assert len(gltf['animations']) == 3
    assert all('uri' not in item for item in gltf['images'] + gltf['buffers'])
    primitive = gltf['meshes'][0]['primitives'][0]
    assert 'JOINTS_0' in primitive['attributes'] and 'WEIGHTS_0' in primitive['attributes']
