"""
Module for ORCID interaction
"""
import requests
headers = {'Accept': 'application/json'}


def search_orcid(orcid):
    """
    Search the ORCID public API

    Specfically, return a dictionary with the personal details
    (name, etc.) of the person associated with the given ORCID

    Args:
        orcid (`str`): The ORCID to be searched

    Returns:
        `dict`: Dictionary with the JSON response from the API

    Raises:
        `~requests.HTTPError`: If the given ORCID cannot be found, an `~requests.HTTPError`
            is raised with status code 404
    """
    url = 'https://pub.orcid.org/v2.1/{orcid}/person'.format(orcid=orcid)
    r = requests.get(url, headers=headers)
    if r.status_code != 200:
        r.raise_for_status()
    return r.json()
