"""Memory by default; optional fresh schemas on the review's temporary Unix-socket PG only."""
import itertools
import os
from urllib.parse import urlsplit, parse_qs
from energy_platform.store import MemoryStore
from energy_platform.store.postgres import PostgresStore
from energy_platform.silver.migrate import create_schema, upgrade
serial=itertools.count(1)
def fresh_store():
    if os.environ.get('REVIEW_USE_POSTGRES') != '1':
        return MemoryStore()
    dsn=os.environ['ENERGY_PLATFORM_TEST_DSN']
    url=urlsplit(dsn)
    host=parse_qs(url.query).get('host',[''])[0]
    assert url.hostname is None and host.startswith('/tmp/ep-pg.'), 'Refusing anything but the review helper temporary DB'
    schema=f'review_probe_{next(serial)}'
    create_schema(dsn,schema)
    upgrade(dsn,schema=schema)
    return PostgresStore(dsn,schema=schema)
