"""Exercise the offline UI on a reserved mechanical code, without a human return."""
from pathlib import Path
import argparse
import json
import shutil
from playwright.sync_api import sync_playwright
import study


def check(executable):
    events, completed = [], []
    with sync_playwright() as engine:
        browser = engine.chromium.launch(executable_path=executable, args=['--no-sandbox'])
        for width, height in [(360, 740), (1280, 800)]:
            context = browser.new_context(viewport={'width': width, 'height': height}, offline=True, accept_downloads=True)
            for code in study.CODES:
                page = context.new_page()
                page.on('pageerror', lambda err: events.append(str(err)))
                page.on('request', lambda req: events.append(req.url) if req.url.startswith(('http:', 'https:')) else None)
                page.goto((study.ROOT / 'packet' / f'{code}.html').as_uri())
                assert not page.locator('#start-form').evaluate('(form) => form.checkValidity()')
                page.locator('#reader').fill('R-000000000000')
                page.locator('#eligible').check()
                page.locator('#start-form button').click()
                assert page.locator('#report').is_visible()
                for i in (1, 2):
                    assert page.locator('#progress').inner_text() == f'報告 {i} / 2'
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                    assert not page.locator('#answer-form').evaluate('(form) => form.checkValidity()')
                    for loc in page.locator('#facts input').all():
                        loc.fill('技術動作確認のみ')
                    page.locator('#choices input').last.check()
                    page.locator('#useful').select_option('3')
                    page.locator('#advance').click()
                with page.expect_download() as dl:
                    page.locator('#download').click()
                actual = json.loads(dl.value.path().read_bytes())
                assert actual == json.loads(page.locator('#copy').input_value())
                assert actual['eligible'] is False and actual['return_type'] == 'mechanical_test'
                assert len(actual['tasks']) == 2 and all(study.screen_timing(x['visible_intervals_ms']) is not None for x in actual['tasks'])
                assert study.decode(actual, code)[0] == 'ineligible_or_test'
                completed.append(f'{width}x{height}/{code}')
                page.close()
            context.close()
        version = browser.version
        browser.close()
    if events:
        raise RuntimeError(events)
    return {'engine': 'Chromium', 'version': version, 'checked': completed, 'offline': True, 'http_requests_and_page_errors': events,
            'validated': ['required fields', 'viewport width', 'two sequential tasks', 'JSON download and copy fallback',
                          'visibility intervals', 'reserved test code excluded'], 'human_returns_created': 0}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--chromium', default=shutil.which('chromium') or shutil.which('google-chrome'))
    args = parser.parse_args()
    print(json.dumps(check(args.chromium), indent=2))
