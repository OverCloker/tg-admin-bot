"""Check the actual CSS cascade with a locally installed headless Chrome."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from app.miniapp_ui import MINI_APP_HTML


def test_shop_and_owned_backgrounds_follow_theme(tmp_path):
    chrome = shutil.which('chromium') or shutil.which('google-chrome')
    if not chrome:
        candidate = Path('C:/Program Files/Google/Chrome/Application/chrome.exe')
        chrome = str(candidate) if candidate.exists() else None
    if not chrome:
        pytest.skip('Headless Chromium not installed')
    css = re.search(r'<style>(.*?)</style>', MINI_APP_HTML, re.S).group(1)
    fixture = '''<div class="shop-screen"><div class="shop-hero"><h2>Магазин</h2><div class="shop-coins">15885</div></div><div class="product"><b class="product-name">Рамка</b><span class="price">2500</span><p class="description">Описание</p></div></div>
    <div class="panel profile-hero bg-old-mine"><h2>Игрок</h2><span class="profile-username">@player</span></div>
    <div class="panel profile-hero bg-lava"></div><div class="panel profile-hero bg-stars"></div>
    <div class="profile-avatar frame-crystal"></div>
    <pre id="result"></pre><script>
    const results={};
    for(const theme of ['classic','glass','expressive']) {
      document.body.dataset.theme=theme;
      const style=s=>getComputedStyle(document.querySelector(s));
      results[theme]={name:style('.product-name').color,coins:style('.shop-coins').color,
        description:style('.description').color,price:style('.price').color,
        surface:style('.shop-screen').backgroundColor,
        backgrounds:['.bg-old-mine','.bg-lava','.bg-stars'].map(s=>style(s).backgroundImage),
        profileText:style('.bg-old-mine h2').color,
        frame:style('.frame-crystal').borderTopColor};
    }
    document.getElementById('result').textContent=JSON.stringify(results);
    </script>'''
    page = tmp_path / 'themes.html'
    page.write_text(f'<html><head><meta charset="utf-8"><style>{css}</style></head><body>{fixture}</body></html>', encoding='utf-8')
    result = subprocess.run([chrome, '--headless', '--disable-gpu', '--no-first-run', '--no-default-browser-check', '--no-proxy-server', '--user-data-dir=' + str(tmp_path / 'browser'), '--dump-dom', page.as_uri()], capture_output=True, timeout=45)
    output = result.stdout.decode('utf-8')
    match = re.search(r'<pre id="result">(.*?)</pre>', output, re.S)
    assert match, result.stderr.decode('utf-8', errors='replace')[-1000:]
    themes = json.loads(match.group(1))
    classic = themes['classic']
    assert classic['surface'] == 'rgb(192, 192, 192)'
    assert classic['name'] == classic['coins'] == 'rgb(0, 0, 0)'
    assert classic['description'] == 'rgb(64, 64, 64)'
    assert classic['price'] == 'rgb(128, 0, 0)'
    for theme in themes.values():
        assert all('gradient' in background for background in theme['backgrounds'])
        assert theme['profileText'] == 'rgb(255, 255, 255)'
    assert themes['classic']['frame'] == themes['expressive']['frame']
    assert themes['glass']['name'] == themes['glass']['coins'] == 'rgb(251, 253, 255)'
    assert themes['expressive']['name'] == themes['expressive']['coins'] == 'rgb(251, 252, 255)'
