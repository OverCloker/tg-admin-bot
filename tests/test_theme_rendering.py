"""Check the actual CSS cascade with a locally installed headless Chrome."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from app.miniapp_ui import MINI_APP_HTML


def run_chrome(chrome, arguments, output_dir, name):
    """Use files instead of Windows pipes, which are flaky under Python 3.14."""
    stdout_path = output_dir / f'{name}.out.html'
    stderr_path = output_dir / f'{name}.err.txt'
    with stdout_path.open('wb') as stdout, stderr_path.open('wb') as stderr:
        result = subprocess.run(
            [chrome, *arguments], stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr, timeout=45,
        )
    return (
        result.returncode,
        stdout_path.read_text(encoding='utf-8'),
        stderr_path.read_text(encoding='utf-8', errors='replace'),
    )


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
    returncode, output, errors = run_chrome(chrome, [
        '--headless=new',
        '--in-process-gpu',
        '--disable-gpu',
        '--disable-features=Vulkan,SkiaGraphite,UseDawn',
        '--no-sandbox',
        '--no-first-run',
        '--no-default-browser-check',
        '--no-proxy-server',
        '--user-data-dir=' + str(tmp_path / 'browser'),
        '--dump-dom',
        page.as_uri(),
    ], tmp_path, 'themes')
    match = re.search(r'<pre id="result">(.*?)</pre>', output, re.S)
    assert returncode == 0, errors[-1000:]
    assert match, errors[-1000:]
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


def test_responsive_layout_for_tablet_orientations_and_desktop(tmp_path):
    chrome = shutil.which('chromium') or shutil.which('google-chrome')
    if not chrome:
        candidate = Path('C:/Program Files/Google/Chrome/Application/chrome.exe')
        chrome = str(candidate) if candidate.exists() else None
    if not chrome:
        pytest.skip('Headless Chromium not installed')
    css = re.search(r'<style>(.*?)</style>', MINI_APP_HTML, re.S).group(1)
    fixture = '''<main><header class="top"><h1>Профиль</h1><button class="top-profile">Назад</button></header>
    <div id="content"><section class="panel">Один</section><section class="panel"><div class="profile-grid"><div class="profile-card">1</div><div class="profile-card">2</div><div class="profile-card">3</div></div></section><section class="panel">Три</section><section class="panel">Четыре</section><section class="panel">Пять</section><section class="panel">Назад</section></div>
    <div class="mine-desktop-layout"><div class="mine-dashboard-column"><section class="panel">Смена</section><section class="panel">Шахта</section></div><div class="mine-dashboard-column"><section class="panel">Сапёр</section><section class="panel">Билет</section><section class="panel">Супер-игра</section></div></div>
    <div class="mine-footer-grid"><section class="panel">Уровень</section><section class="panel">Сумка</section></div>
    <div class="shop-products"><div class="product">Товар 1</div><div class="product">Товар 2</div></div>
    <div class="inventory"><div>Предмет 1</div><div>Предмет 2</div></div></main>
    <pre id="result"></pre><script>
    const style = node => getComputedStyle(node);
    const columns = value => value.split(/\\s+/).filter(Boolean).length;
    const source = document.createElement('div');
    source.className = 'alarm-source-track';
    source.innerHTML = '<label>Alerts.in.ua</label><label>NEPTUN</label><label>UkraineAlarm</label>';
    document.querySelector('.panel').appendChild(source);
    document.getElementById('result').textContent=JSON.stringify({
      viewport: innerWidth,
      mainWidth: document.querySelector('main').getBoundingClientRect().width,
      contentDisplay: style(document.getElementById('content')).display,
      contentColumns: columns(style(document.getElementById('content')).gridTemplateColumns),
      contentAlign: style(document.getElementById('content')).alignItems,
      profileColumns: columns(style(document.querySelector('.profile-grid')).gridTemplateColumns),
      mineColumns: columns(style(document.querySelector('.mine-desktop-layout')).gridTemplateColumns),
      mineFooterColumns: columns(style(document.querySelector('.mine-footer-grid')).gridTemplateColumns),
      shopColumns: columns(style(document.querySelector('.shop-products')).gridTemplateColumns),
      inventoryColumns: columns(style(document.querySelector('.inventory')).gridTemplateColumns),
      lastContentSpan: style(document.querySelector('#content > .panel:nth-last-child(2)')).gridColumnEnd,
      overflow: document.documentElement.scrollWidth > innerWidth,
      labelOverflow: style(source.querySelector('label:last-child')).overflow
    });
    </script>'''

    def render(width, height):
        page = tmp_path / f'layout-{width}-{height}.html'
        page.write_text(
            f'<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>{css}</style></head><body data-view="profile">{fixture}</body></html>',
            encoding='utf-8',
        )
        returncode, output, errors = run_chrome(chrome, [
            '--headless=new', '--in-process-gpu', '--disable-gpu',
            '--disable-features=Vulkan,SkiaGraphite,UseDawn', '--no-sandbox',
            '--no-first-run', '--no-default-browser-check', '--no-proxy-server',
            f'--window-size={width},{height}', '--force-device-scale-factor=1',
            '--user-data-dir=' + str(tmp_path / f'browser-{width}-{height}'),
            '--dump-dom', page.as_uri(),
        ], tmp_path, f'layout-{width}-{height}')
        match = re.search(r'<pre id="result">(.*?)</pre>', output, re.S)
        assert returncode == 0, errors[-1000:]
        assert match, errors[-1000:]
        return json.loads(match.group(1))

    portrait = render(800, 1100)
    landscape = render(1024, 700)
    desktop = render(1440, 900)
    assert portrait['contentDisplay'] == 'block'
    assert 700 <= portrait['mainWidth'] <= 760
    assert portrait['profileColumns'] == 3
    assert portrait['mineColumns'] == portrait['mineFooterColumns'] == 1
    for layout in (landscape, desktop):
        assert layout['contentDisplay'] == 'grid'
        assert layout['contentColumns'] == 2
        assert layout['contentAlign'] == 'stretch'
        assert layout['profileColumns'] == 3
        assert layout['mineColumns'] == 2
        assert layout['mineFooterColumns'] == 2
        assert layout['shopColumns'] == 2
        assert layout['inventoryColumns'] == 2
        assert layout['lastContentSpan'] == '-1'
        assert layout['overflow'] is False
        assert layout['labelOverflow'] == 'hidden'
    assert 1000 <= desktop['mainWidth'] <= 1060
