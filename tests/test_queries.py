# encoding: utf-8
#

import pytest
from valis.db.queries import convert_coords


@pytest.mark.parametrize('ra, dec, exp',
                         [('315.01417', '35.299', (315.01417, 35.299)),
                          ('315.01417', '-35.299', (315.01417, -35.299)),
                          (315.01417, -35.299, (315.01417, -35.299)),
                          ('21h00m03.4008s', '+35d17m56.4s', (315.01417, 35.299)),
                          ('21:00:03.4008', '+35:17:56.4', (315.01417, 35.299)),
                          ('21 00 03.4008', '+35 17 56.4', (315.01417, 35.299)),
                          ],
                         ids=['dec1', 'dec2', 'dec3', 'hms1', 'hms2', 'hms3'])
def test_convert_coords(ra, dec, exp):
    """ test we can convert coordinates correctly """
    coord = convert_coords(ra, dec)
    assert coord == exp




