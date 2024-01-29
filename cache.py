import json
from datetime import datetime, timedelta


class CachedAPI:
    def __init__(self, cache_file, cache_time_minutes):
        self.cache_time_minutes = cache_time_minutes
        self.cache_file = cache_file
        self.cache = None
        self.load_cache()

    def load_cache(self):
        try:
            with open(self.cache_file, 'r') as file:
                self.cache = json.load(file)
        except FileNotFoundError:
            self.cache = {}

    def save_cache(self):
        with open(self.cache_file, 'w') as file:
            json.dump(self.cache, file, indent=4)

    def is_cache_stale(self, cache_key):
        """
        Vérifie si le cache est obsolète.

        :param cache_key: la clé du cache à vérifier
        :return: bool, True si le cache est obsolète, False sinon
        """
        if cache_key in self.cache:
            timestamp = self.cache[cache_key]['timestamp']
            cache_time = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S")
            return datetime.now() - cache_time > timedelta(minutes=self.cache_time_minutes)
        return True

    def get_cached_data(self, cache_key, retrieval_function, *args, **kwargs):
        if self.is_cache_stale(cache_key):
            print(f"The cache needs to be renewed...")
            new_data = retrieval_function(*args, **kwargs)

            if new_data:
                self.cache[cache_key] = {
                    'data': new_data,
                    'timestamp': datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
                }
                self.save_cache()

            return new_data

        if cache_key in self.cache:
            return self.cache[cache_key]['data']

        return None