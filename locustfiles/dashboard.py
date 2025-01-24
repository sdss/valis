import random
from locust import HttpUser, task, between


# A set of files to run with [locust.io](https://locust.io/) for performance testing the dashboard.
# pip install locust
# then run "locust -f dashboard.py" and open http://localhost:8089/ in your browser


class DashUser(HttpUser):
    release = 'dr19'
    #sdssids = [23326, 54392544, 57651832, 57832526, 61731453, 85995134, 56055457]
    wait_time = between(1, 5)  # Simulate user think time between requests

    data_types = ['star', 'visit']
    #plot_types = ['scatter', 'heatmap', 'skyplot', 'histogram', 'stats']
    #data_sets = ['best', 'apogeenet', 'thepayne', 'bossnet', 'aspcap', 'bhm', 'slam']

    plot_types = ['scatter', 'heatmap']
    data_sets = ['apogeenet', 'thepayne']
    carton = ['mwm_halo_local,ops_sky', 'mwm_snc_openfiber,mwm_erosita_stars', 'manual_mwm_planet_tess_pc',
              'mwm_halo_distant_rrl','mwm_yso_cluster,mwm_ob_core']
    x = ['teff', 'g_mag', 'u_sdss_mag', 'snr']
    y = ['logg', 'fe_h', 'g_mag', 'k_mag']
    color = ['fe_h','snr', 'ebv']

    @task
    def query_dashboard(self):
        """ simulate a user generating a single plot on the dashboard """
        url = "/solara/dashboard"
        params = {'release': self.release,
                  'datatype': random.choice(self.data_types),
                  'dataset': random.choice(self.data_sets),
                  'plottype': random.choice(self.plot_types),
                  'carton': random.choice(self.carton),
                  'x': random.choice(self.x),
                  'y': random.choice(self.y),
                  'color': random.choice(self.color)
                  }
        with self.client.get(url, params=params, catch_response=True) as response:
            if response.status_code != 200:
                response.failure(f"GET {url} failed: {response.text}")

# if __name__ == "__main__":
#     run_single_user(DashUser)