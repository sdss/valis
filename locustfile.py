import random
from locust import HttpUser, task, between


# A set of files to run with [locust.io](https://locust.io/) for performance testing the app.
# pip install locust
# then run "locust -f locustfile.py" and open http://localhost:8089/ in your browser


class FastAPIUser(HttpUser):
    release = 'IPL3'
    sdssids = [23326, 54392544, 57651832, 57832526, 61731453, 85995134, 56055457]
    wait_time = between(1, 5)  # Simulate user think time between requests

    @task
    def query_main(self):
        url = "/query/main"
        headers = {'Content-Type': 'application/json'}
        params = {'release': self.release}
        payload1 = {
            'ra': random.uniform(0, 360),
            'dec': random.uniform(-90, 90),
            'radius': random.uniform(0.01, 0.2),
            'units': 'degree',
            'observed': True
        }
        payload2 = {
            "id": random.choice(self.sdssids),
        }
        payload3 = {
            'ra': random.uniform(0, 360),
            'dec': random.uniform(-90, 90),
            'radius': random.uniform(0.01, 0.2),
            'units': 'degree',
            'observed': True,
            'program': 'bhm_rm',
            'carton': 'bhm_rm_core'
        }
        payload = random.choice([payload1, payload2, payload3])
        with self.client.post(url, headers=headers, params=params, json=payload, catch_response=True) as response:
            if response.status_code != 200:
                response.failure(f"POST {url} failed: {response.text}")

    @task
    def query_cone(self):
        url = "/query/cone"
        params = {
            'ra': random.uniform(0, 360),
            'dec': random.uniform(-90, 90),
            'radius': random.uniform(0.01, 0.5),
            'units': 'degree',
            'observed': random.choice([True, False]),
            'release': self.release
        }
        with self.client.get(url, params=params, catch_response=True) as response:
            if response.status_code != 200:
                response.failure(f"GET {url} failed: {response.text}")

    @task
    def query_carton(self):
        url = '/query/carton-program'
        params = {
            'name': 'manual_mwm_tess_ob',
            'name_type': 'carton',
            'observed': True,
            'release': self.release
        }
        with self.client.get(url, params=params, catch_response=True) as response:
            if response.status_code != 200:
                response.failure(f"GET {url} failed: {response.text}")

    @task
    def get_spectrum(self):
        sdss_id = 23326
        url = f"/target/spectra/{sdss_id}"
        params = {
            'product': 'specLite',
            'ext': 'BOSS/APO',
            'release': self.release
        }
        with self.client.get(url, params=params, catch_response=True) as response:
            if response.status_code != 200:
                response.failure(f"GET {url} failed: {response.text}")

    @task
    def get_catalogs(self):
        sdss_id = random.choice(self.sdssids)
        url = f"/target/catalogs/{sdss_id}"
        params = {'release': self.release}
        with self.client.get(url, params=params, catch_response=True) as response:
            if response.status_code != 200:
                response.failure(f"GET {url} failed: {response.text}")

    @task
    def get_parents(self):
        catalog = 'gaia_dr3_source'
        sdss_id = 129047350
        url = f"/target/parents/{catalog}/{sdss_id}"
        params = {
            'catalogid': 63050396587194280,
            'release': self.release
        }
        with self.client.get(url, params=params, catch_response=True) as response:
            if response.status_code != 200:
                response.failure(f"GET {url} failed: {response.text}")

    @task
    def get_cartons(self):
        sdss_id = random.choice(self.sdssids)
        url = f"/target/cartons/{sdss_id}"
        params = {'release': self.release}
        with self.client.get(url, params=params, catch_response=True) as response:
            if response.status_code != 200:
                response.failure(f"GET {url} failed: {response.text}")

    @task
    def get_pipelines(self):
        sdss_id = random.choice(self.sdssids)
        url = f"/target/pipelines/{sdss_id}"
        params = {
            'release': self.release
        }
        with self.client.get(url, params=params, catch_response=True) as response:
            if response.status_code != 200:
                response.failure(f"GET {url} failed: {response.text}")

# if __name__ == "__main__":
#     run_single_user(FastAPIUser)