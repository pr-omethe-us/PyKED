"""Module for ORCID interaction"""

import httpx

headers = {"Accept": "application/json"}


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
        `~httpx.HTTPStatusError`: If the given ORCID cannot be found, an
            `~httpx.HTTPStatusError` is raised with status code 404
    """
    url = f"https://pub.orcid.org/v3.0/{orcid}/person"
    r = httpx.get(url, headers=headers)
    r.raise_for_status()
    return r.json()
