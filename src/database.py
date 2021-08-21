from redis import Redis


class Database(object):
    def __init__(self, db: int = 0, **kwargs):
        self._redis = Redis(host=kwargs.get('config')['redis']['host'],
                            port=kwargs.get('config')['redis']['port'],
                            username=kwargs.get('config')['redis']['username'],
                            password=kwargs.get('config')['redis']['password'],
                            db=db)

    def add_user(self, id: int, force=False):
        if not self.contains_user(id) or force:
            data = {
                'server': '',
                'user': '',
                'password': '',
                'cwd': '/',
                'split_size': 100,
                'upload_path': '/',
                'upload_parallel': 'off'
            }

            self.set_data(id, **data)
            return True

        return False

    def get_data(self, id: int):
        return {
            k.decode('utf-8'): v.decode('utf-8')
            for k, v in self._redis.hgetall(f'user:{id}').items()
        }

    def set_data(self, id: int, **kwargs):
        # print(kwargs)
        for k, v in kwargs.items():
            self._redis.hset(f'user:{id}', key=k, value=v)

    def contains_user(self, id: int):
        return self._redis.exists(f'user:{id}')