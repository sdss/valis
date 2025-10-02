.. _valis-changelog:

==========
Change Log
==========

0.2.0 (10-02-2025)
------------------
* Adds endpoint for getting a BHM spectrum (POC)
* Adds endpoint for getting target pipeline metadata for sdss_id
* Adds endpoints for target search by sdss_id and catalogid
* Adds endpoints for listing cartons and programs
* Adds endpoints for target search by carton and program
* Adds ``db_reset`` option to avoid closing and resetting the database connection
* Updates main, cone, and carton/program search to use new ``has_been_observed`` column; default is True.
* Updates the ``append_pipes`` query to return the new ``has_been_observed`` column
* Include parent catalog associations in the ``/target/catalogs`` endpoint (#37).
* Adds endpoint to get parent catalog data for a given target (#38).
* Support for astra dr17 apogee spectra (#57)
* Adds endpoint for getting list of parent catalogs (#40)
* Adds endpoint for querying parent catalogs (#43)
* Adds cross-match separation distance to search results (#54)
* Adds mocs and hips catalogs endpoints (#51)
* Adds endpoint for searching for alternate target IDs (#61)
* Fixes byteorder encoding issue (#65, #66)
* Adds support for mwmVisit files (#68)
* Adds mjd cutoff for release quering (#72)
* Adds route endpoint caching (#73)
* Updates auth to more endpoints (#75)
* Fix for LCO hack (#78)
* Prep for DR19 (#80)
* Adds endpoint for quering legacy info via allspec (#83)

0.1.0 (10-24-2023)
------------------
* Initial tag of software
* Adds example query endpoint for cone searches against ``vizdb``
* Adds initial connection to databases with ``sdssdb``
* Adds endpoint for interacting with SDSS maskbits
* Adds endpoint for resolving target names and coordinates with Simbad
* Adds initial endpoint for retrieving SDSS MOCs
* Adds SDSS authentication with Wiki credentials for WORK release
* Adds endpoint for looking up SDSS datamodels
* Adds endpoint for downloading or streaming FITS file data
* Adds endpoint for accessing ``tree`` and ``sdss_access`` environment and path info
* Sets up main FastAPI architecture
