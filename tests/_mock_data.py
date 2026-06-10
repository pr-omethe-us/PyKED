"""Shared mock data for Crossref and ORCID APIs used by conftest.py and test_live_api.py."""

CROSSREF_RESPONSES = {
    "10.1016/j.ijhydene.2007.04.008": {
        "container-title": ["International Journal of Hydrogen Energy"],
        "published-print": {"date-parts": [[2007]]},
        "volume": "32",
        "page": "2216-2226",
        "author": [
            {"given": "N.", "family": "Chaumeix"},
            {"given": "S.", "family": "Pichon"},
            {"given": "F.", "family": "Lafosse"},
            {"given": "C.-E.", "family": "Paillard"},
        ],
    },
    "10.1002/kin.20180": {
        "container-title": ["International Journal of Chemical Kinetics"],
        "published-print": {"date-parts": [[2006]]},
        "volume": "38",
        "page": "516-529",
        "author": [
            {"given": "Gaurav", "family": "Mittal"},
            {
                "given": "Chih-Jen",
                "family": "Sung",
                "ORCID": "http://orcid.org/0000-0003-2046-8076",
            },
            {"given": "Richard A.", "family": "Yetter"},
        ],
    },
    # No "volume" or "page" — tested by test_no_volume_in_DOI and test_no_page_in_DOI
    "10.1115/GT2013-94282": {
        "container-title": ["Volume 1A: Combustion, Fuels and Emissions"],
        "published-print": {"date-parts": [[2013]]},
        "author": [
            {"given": "F.", "family": "Xu"},
            {"given": "V.", "family": "Nori"},
            {"given": "J.", "family": "Basani"},
        ],
    },
    "10.1016/j.combustflame.2011.08.014": {
        "container-title": ["Combustion and Flame"],
        "published-print": {"date-parts": [[2012]]},
        "volume": "159",
        "page": "516-527",
        "author": [
            {"given": "Ivo", "family": "Stranic"},
            {"given": "Deanna P.", "family": "Chase"},
            {"given": "Joseph T.", "family": "Harmon"},
            {"given": "Sheng", "family": "Yang"},
            {"given": "David F.", "family": "Davidson"},
            {"given": "Ronald K.", "family": "Hanson"},
        ],
    },
    # Tested by test_suggest_ORCID, test_missing_author, test_extra_authors, test_unmatching_ORCIDs
    "10.1016/j.combustflame.2015.06.017": {
        "container-title": ["Combustion and Flame"],
        "published-print": {"date-parts": [[2015]]},
        "volume": "162",
        "page": "3596-3611",
        "author": [
            {
                "given": "Kyle E.",
                "family": "Niemeyer",
                "ORCID": "http://orcid.org/0000-0003-4425-7097",
            },
            {"given": "Kyle", "family": "Brady"},
            {"given": "Chih-Jen", "family": "Sung"},
            {"given": "Xin", "family": "Hui"},
        ],
    },
    # Tested by test_two_authors_same_surname, test_wrong_year/journal/volume/page
    "10.1016/j.combustflame.2013.08.018": {
        "container-title": ["Combustion and Flame"],
        "published-print": {"date-parts": [[2014]]},
        "volume": "161",
        "page": "127-137",
        "author": [
            {"given": "Zhuyin", "family": "Ren"},
            {"given": "Yufeng", "family": "Liu"},
            {"given": "Liuyan", "family": "Lu"},
            {"given": "Tianfeng", "family": "Lu"},
            {"given": "Oluwayemisi O.", "family": "Oluwole"},
            {"given": "Graham M.", "family": "Goldin"},
        ],
    },
    # Tested by TestGetReference::test_doi_author_orcid
    "10.1016/j.cpc.2017.02.004": {
        "container-title": ["Computer Physics Communications"],
        "published-print": {"date-parts": [[2017]]},
        "volume": "215",
        "page": "188-203",
        "author": [
            {
                "given": "Kyle E.",
                "family": "Niemeyer",
                "ORCID": "http://orcid.org/0000-0003-4425-7097",
            },
            {
                "given": "Nicholas J.",
                "family": "Curtis",
                "ORCID": "http://orcid.org/0000-0002-0303-4711",
            },
            {"given": "Chih-Jen", "family": "Sung"},
        ],
    },
}

CROSSREF_INVALID_DOIS = {"10.1000/invalid.doi"}

ORCID_RESPONSES = {
    # given-names must be "Kyle" (not "Kyle E.") — test_invalid_ORCID_name expects
    # "Name associated with ORCID: Kyle Niemeyer"
    "0000-0003-4425-7097": {
        "name": {
            "family-name": {"value": "Niemeyer"},
            "given-names": {"value": "Kyle"},
        }
    },
    # Used by testfile_st_p5.yaml file-author
    "0000-0001-7137-5721": {
        "name": {
            "family-name": {"value": "Mayer"},
            "given-names": {"value": "Morgan"},
        }
    },
    # Used in testfile_rcm.yaml and testfile_rcm2.yaml reference.authors
    "0000-0003-2046-8076": {
        "name": {
            "family-name": {"value": "Sung"},
            "given-names": {"value": "Chih-Jen"},
        }
    },
    # Used in test_valid_reference_authors and test_unmatching_ORCIDs
    "0000-0003-0815-9270": {
        "name": {
            "family-name": {"value": "Weber"},
            "given-names": {"value": "Bryan"},
        }
    },
    # Used in test_suggest_ORCID, test_missing_author, test_extra_authors, test_unmatching_ORCIDs
    "0000-0002-4664-3680": {
        "name": {
            "family-name": {"value": "Brady"},
            "given-names": {"value": "Kyle"},
        }
    },
}
