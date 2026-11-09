"""Fail early for enabled publication without printing secret values."""
import os

REQUIRED = ('YOUTUBE_TOKEN_JSON', 'EXPECTED_CHANNEL_ID', 'DRIVE_TOKEN_JSON', 'DRIVE_FOLDER_ID')


def validate(environment=None):
    environment = os.environ if environment is None else environment
    if environment.get('FACEBOOK_PUBLISH_ENABLED') == 'true' and not environment.get('FACEBOOK_PAGE_ACCESS_TOKEN', '').strip():
        print('::warning::Facebook token is missing; optional Facebook publication may fail. YouTube generation and publication will continue.')
    if environment.get('PUBLISH_ENABLED') != 'true':
        return
    missing = [name for name in REQUIRED if not environment.get(name, '').strip()]
    if missing:
        raise ValueError('Publishing is enabled but required repository secrets are missing: ' + ', '.join(missing))


if __name__ == '__main__':
    try:
        validate()
    except ValueError as error:
        raise SystemExit(str(error)) from None
