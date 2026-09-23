from app.models import VesselIdentity
from app.vessel_photos import VesselPhotoCatalog


def test_catalog_downloads_and_reuses_exact_imo_photo(tmp_path, monkeypatch):
    catalog = VesselPhotoCatalog(tmp_path / "photos")
    vessel = VesselIdentity(name="TEST VESSEL", imo="1234567", mmsi=["123456789"])
    calls = []

    def api(params):
        calls.append(params)
        if params.get("list") == "search":
            return {
                "query": {
                    "search": [
                        {"ns": 6, "title": "File:Other vessel.jpg"},
                        {"ns": 6, "title": "File:Test vessel (IMO 1234567).jpg"},
                    ]
                }
            }
        if params.get("list") == "categorymembers":
            return {"query": {"categorymembers": []}}
        return {
            "query": {
                "pages": {
                    "1": {
                        "title": "File:Test vessel (IMO 1234567).jpg",
                        "imageinfo": [
                            {
                                "mime": "image/jpeg",
                                "thumburl": "https://thumb.wikimedia.org/test.jpg",
                                "descriptionurl": "https://commons.wikimedia.org/wiki/File:Test_vessel_(IMO_1234567).jpg",
                                "extmetadata": {
                                    "LicenseShortName": {"value": "CC BY-SA 4.0"},
                                    "LicenseUrl": {"value": "https://creativecommons.org/licenses/by-sa/4.0/"},
                                    "Artist": {"value": '<a href="/user">Test Photographer</a>'},
                                },
                            }
                        ],
                    }
                }
            }
        }

    monkeypatch.setattr(catalog, "_api_json", api)
    monkeypatch.setattr(catalog, "_image_bytes", lambda url: b"\xff\xd8\xfftest")

    image = catalog.image_for(vessel)
    assert image["src"] == "/vessel-photos/123456789.jpg"
    assert image["credit"] == "Test Photographer · CC BY-SA 4.0"
    assert (tmp_path / "photos" / "123456789.jpg").read_bytes() == b"\xff\xd8\xfftest"

    previous_calls = len(calls)
    assert catalog.image_for(vessel) == image
    assert len(calls) == previous_calls


def test_catalog_rejects_unverified_or_unlicensed_images(tmp_path, monkeypatch):
    catalog = VesselPhotoCatalog(tmp_path / "photos")
    vessel = VesselIdentity(name="TEST VESSEL", imo="1234567", mmsi=["123456789"])

    def api(params):
        if params.get("list") == "search":
            return {
                "query": {
                    "search": [
                        {"ns": 6, "title": "File:Unrelated vessel.jpg"},
                        {"ns": 6, "title": "File:Test vessel (IMO 1234567).jpg"},
                    ]
                }
            }
        if params.get("list") == "categorymembers":
            return {"query": {"categorymembers": []}}
        assert params["titles"] == "File:Test vessel (IMO 1234567).jpg"
        return {
            "query": {
                "pages": {
                    "1": {
                        "title": "File:Test vessel (IMO 1234567).jpg",
                        "imageinfo": [
                            {"mime": "image/jpeg", "extmetadata": {"LicenseShortName": {"value": "All rights reserved"}}}
                        ],
                    }
                }
            }
        }

    monkeypatch.setattr(catalog, "_api_json", api)
    monkeypatch.setattr(
        catalog, "_image_bytes", lambda url: (_ for _ in ()).throw(AssertionError("not allowed"))
    )

    assert catalog.image_for(vessel)["src"] == "/static/vessels/vessel-placeholder.svg"
    assert not list((tmp_path / "photos").glob("*.jpg"))
