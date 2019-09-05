import json
import traceback
from contextlib import contextmanager
import os
import random
import signal
import string
from time import sleep
from datetime import datetime

import psycopg2


LEGAL_CHARS = string.ascii_letters + ' '

LARGE_BATCH_SIZE = 1000
SMALL_BATCH_SIZE = 2

TABLE_PREFIX = os.environ.get('DB_TABLE_PREFIX', '')

PARAMS = {
    "user": os.environ.get("DB_USER"),
    "password": os.environ.get("DB_PASSWORD"),
    "database": os.environ.get("DB_DATABASE"),
    "host": os.environ.get("DB_HOST"),
    "port": os.environ.get("DB_PORT")
}

CREATE_INITIAL_TABLES = '''
CREATE TABLE IF NOT EXISTS {table_prefix}test1 (id bigserial primary key, col2 int, col3 varchar(512), col4 text, col5 text, col6 text);
CREATE TABLE IF NOT EXISTS {table_prefix}test2 (id bigserial primary key, test1_id bigint, col2 int, col3 text);
'''.format(table_prefix=TABLE_PREFIX)


class TermSignalHandler:
  kill_now = False
  def __init__(self):
    signal.signal(signal.SIGINT, self.exit_gracefully)
    signal.signal(signal.SIGTERM, self.exit_gracefully)

  def exit_gracefully(self,signum, frame):
    self.kill_now = True


def ts():
    return str(datetime.utcnow())


@contextmanager
def get_connection():
    connection = psycopg2.connect(**PARAMS)
    yield connection
    connection.close()


def execute(query, return_results=False):
    with get_connection() as connection, connection.cursor() as cursor:
        cursor.execute(query)
        connection.commit()
        if return_results:
            return cursor.fetchall()


def generate_random_string(max_length):
    length = random.randint(0, max_length)
    return ''.join(random.choice(LEGAL_CHARS) for i in range(length))


def insert_batch(batch_size):
    data = []
    for j in range(batch_size):
        col2 = random.randint(0, 190000)
        col3 = generate_random_string(500)
        col4 = generate_random_string(2500)
        col5 = generate_random_string(2500)
        col6 = generate_random_string(2500)
        data.append("({}, '{}', '{}', '{}', '{}')".format(col2, col3, col4, col5, col6))
    execute("insert into {}test1 (col2, col3, col4, col5, col6) values {}".format(TABLE_PREFIX, ','.join(data)))


def create_foreign_key_batch(batch_size):
    rows = execute('select id from {}test1 order by random() limit {}'.format(TABLE_PREFIX, batch_size), return_results=True)
    some_ids = [row[0] for row in rows]
    data = ["({}, {}, '{}')".format(_id, random.randint(0, 190000), generate_random_string(2500)) for _id in some_ids]
    execute("insert into {}test2 (test1_id, col2, col3) values {}".format(TABLE_PREFIX, ','.join(data)))
    #execute("delete from test2 where test1_id not in (select id from test1)")


def initial_data_insert():
    for i in range(100):
        insert_batch(LARGE_BATCH_SIZE)
        create_foreign_key_batch(LARGE_BATCH_SIZE)


def insert_data_small():
    insert_batch(SMALL_BATCH_SIZE)
    create_foreign_key_batch(SMALL_BATCH_SIZE)


def insert_data_large():
    insert_batch(LARGE_BATCH_SIZE)
    create_foreign_key_batch(LARGE_BATCH_SIZE)


def select_data_small():
    _ = execute("select * from {}test1 order by random() limit {}".format(TABLE_PREFIX, SMALL_BATCH_SIZE), return_results=True)


def select_data_large():
    _ = execute("select * from {}test1 order by random() limit {}".format(TABLE_PREFIX, LARGE_BATCH_SIZE), return_results=True)


def select_data_with_join_small():
    _ = execute("select * from {table_prefix}test2 join {table_prefix}test1 "
                "on test1_id = {table_prefix}test1.id limit {batch_size}".format(
        table_prefix=TABLE_PREFIX, batch_size=SMALL_BATCH_SIZE), return_results=True)


def select_data_with_join_large():
    _ = execute("select * from {table_prefix}test2 join {table_prefix}test1 "
                "on test1_id = {table_prefix}test1.id limit {batch_size}".format(
        table_prefix=TABLE_PREFIX, batch_size=LARGE_BATCH_SIZE), return_results=True)


def delete_data_small():
    execute('delete from {table_prefix}test1 where id in (select id from {table_prefix}test1 order by random() limit {batch_size})'.format(
        table_prefix=TABLE_PREFIX, batch_size=SMALL_BATCH_SIZE))
    execute('delete from {table_prefix}test2 where id in (select id from {table_prefix}test2 order by random() limit {batch_size})'.format(
        table_prefix=TABLE_PREFIX, batch_size=SMALL_BATCH_SIZE))
    #execute('delete from test2 where test1_id not in (select id from test1)')

def delete_data_large():
    execute('delete from {table_prefix}test1 where id in (select id from {table_prefix}test1 order by random() limit {batch_size})'.format(
        table_prefix=TABLE_PREFIX, batch_size=LARGE_BATCH_SIZE))
    execute('delete from {table_prefix}test2 where id in (select id from {table_prefix}test2 order by random() limit {batch_size})'.format(
        table_prefix=TABLE_PREFIX, batch_size=LARGE_BATCH_SIZE))
    #execute('delete from test2 where test1_id not in (select id from test1)')


def balance_tables():
    test1_count = execute('select count(*) from {table_prefix}test1'.format(table_prefix=TABLE_PREFIX), return_results=True)[0][0]
    if test1_count < 100000:
        insert_batch(1000)
    else:
        execute('delete from {table_prefix}test1 where id in (select id from {table_prefix}test1 order by random() limit {batch_size})'.format(
            table_prefix=TABLE_PREFIX, batch_size=LARGE_BATCH_SIZE))
    test2_count = execute('select count(*) from {table_prefix}test2'.format(table_prefix=TABLE_PREFIX), return_results=True)[0][0]
    if test2_count < 100000:
        create_foreign_key_batch(1000)
    else:
        execute('delete from {table_prefix}test2 where id in (select id from {table_prefix}test2 order by random() limit {batch_size})'.format(
            table_prefix=TABLE_PREFIX, batch_size=LARGE_BATCH_SIZE))



FUNCTIONS = [
    insert_data_small,
    insert_data_large,
    select_data_small,
    select_data_large,
    select_data_with_join_large,
    select_data_with_join_small,
    delete_data_large,
    delete_data_small,
    balance_tables,
    balance_tables,
]


def run_test():
    term_signal_handler = TermSignalHandler()
    while not term_signal_handler.kill_now:
        fn = random.choice(FUNCTIONS)
        try:
            print(json.dumps({'ts': ts(), 'db_host': PARAMS['host'], 'event': 'attempt', 'severity': 'info', 'function': fn.__name__}))
            fn()
        except psycopg2.OperationalError:
            print(json.dumps({'ts': ts(), 'db_host': PARAMS['host'], 'event': 'operationalerror', 'severity': 'error', 'function': fn.__name__, 'traceback': traceback.format_exc()}))
        except:
            print(json.dumps({'ts': ts(), 'db_host': PARAMS['host'], 'event': 'error', 'severity': 'error', 'function': fn.__name__, 'traceback': traceback.format_exc()}))


def main():
    print(json.dumps({'ts': ts(), 'db_host': PARAMS['host'], 'event': 'initializing', 'severity': 'info', 'message': 'sleeping 10 seconds to give cloudsql chance to startup'}))
    sleep(10)
    if os.environ.get('DO_INITIALIZATION', 'false').upper() == 'TRUE':
        print(json.dumps({'ts': ts(), 'db_host': PARAMS['host'], 'event': 'initializing', 'severity': 'info', 'message': 'creating tables and writing initial data'}))
        execute(CREATE_INITIAL_TABLES)
        initial_data_insert()
    for fn in FUNCTIONS:
        print(json.dumps({'ts': ts(), 'db_host': PARAMS['host'], 'event': 'testing', 'severity': 'info', 'function': fn.__name__}))
        fn()
    run_test()


if __name__ == '__main__':
    main()
