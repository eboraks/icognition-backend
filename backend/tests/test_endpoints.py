import time
import requests
import urllib.parse as urlparse
from typing import List

""" Generate unit test for endpoints.py FastAPI functions """


base_url = (
    "http://127.0.0.1:8889"  # "https://icognition-api-scv-5csjr6fjpa-uc.a.run.app"
)

url = "https://www.yahoo.com/sports/march-madness-no-11-duquesne-upsets-no-6-byu-for-first-tournament-win-in-over-50-years-185918242.html"
payload = {"url": url, "user_id": "7778888"}

# Unit test for create bookmart


# use requests to call /bookmark endpoint with jpage as payload
# check response status code
# check response content
def test_bookmark_end_to_end_workflow():
    """
    Test the end-to-end workflow of bookmarking a document.

    This test performs the following steps:
    1. Encodes the URL in the payload.
    2. Sends a GET request to retrieve bookmarks with the encoded URL as a parameter.
    3. Checks the status code of the response.
    4. If the status code is 200, retrieves the bookmark ID from the response and sends a DELETE request to delete the document associated with the bookmark.
    5. Checks the status code of the delete request response.
    6. Sends a POST request to create a new bookmark with the payload.
    7. Checks the status code of the create request response.
    8. Retrieves the bookmark ID and document ID from the response.
    9. Checks that the bookmark ID is not None.
    10. Encodes the URL in the payload again.
    11. Sends a GET request to retrieve bookmarks with the encoded URL as a parameter.
    12. Checks the status code of the response.
    13. Enters a loop to retrieve the document associated with the bookmark.
    14. Checks the status code of the response.
    15. If the status code is 206 and the counter is less than 3, waits for 2 seconds and repeats step 13.
    16. If the status code is 200, exits the loop and checks that the document title is not None.
    17. If the status code is neither 206 nor 200, exits the loop and asserts False.
    """
    url = urlparse.quote(payload["url"], safe="")
    params = {"url": url}
    response = requests.get(f"{base_url}/bookmark", params=params)
    status_code = response.status_code
    if status_code == 200:
        bookmark_id = response.json()["id"]
        response = requests.delete(f"{base_url}/bookmark/{bookmark_id}/document")
        status_code = response.status_code
        assert status_code == 204

    ## Test creating bookmark
    response = requests.post(f"{base_url}/bookmark", json=payload)
    assert response.status_code == 201
    bookmark_id = response.json()["id"]
    document_id = response.json()["document_id"]
    assert bookmark_id != None

    ## Test getting the bookmark
    url = urlparse.quote(payload["url"], safe="")
    params = {"url": url}
    response = requests.get(f"{base_url}/bookmark", params=params)
    status_code = response.status_code
    assert status_code == 200

    ## Test waiting for the document to be ready.
    loop_condition = True  # Loop until the condition is False
    counter = 0  # Counter to keep track of the number of iterations
    while loop_condition:
        counter += 1
        response = requests.get(f"{base_url}/document_plus/{bookmark_id}")

        print(f"Response status code: {response.status_code}. counter: {counter}")
        if response.status_code == 206 and counter < 10:
            time.sleep(4)
        elif response.status_code == 200:
            loop_condition = False
            doc = response.json()
            assert doc["title"] is not None
        else:
            loop_condition = False
            assert False


def test_create_bookmark_not_found():
    url = "https://www.google.com/"
    payload = {"url": url, "user_id": "7778tyr88"}
    response = requests.post(f"{base_url}/bookmark", json=payload)
    print(f"Test create bookmark not found response {response.json()}")
    status_code = response.status_code
    detail = response.json()["detail"]
    assert detail == "I am sorry, I can't analyze home pages"
    assert status_code == 400


def test_get_bookmark_not_found():
    url = urlparse.quote("https://www.google.com", safe="")
    params = {"url": url}
    response = requests.get(f"{base_url}/bookmark", params=params)
    print(f"Test get bookmark not found response {response.json()}")
    status_code = response.status_code
    assert status_code == 404


def test_get_bookmarks_per_user():
    response = requests.get(f"{base_url}/bookmark/user/777")
    assert response.status_code == 200
    bookmarks = response.json()
    assert len(bookmarks) > 0


def xtest_get_document():
    response = requests.post(f"{base_url}/bookmark", json=payload)
    id = response.json()["document_id"]
    response = None
    response = requests.get(f"{base_url}/document/{id}")
    assert response.status_code == 200


def test_document_regeration():
    ## get document by url
    bookmark_response = requests.get(f"{base_url}/bookmark", params={"url": url})
    bookmark = bookmark_response.json()
    assert bookmark != None

    # get document by document id
    doc_response = requests.get(f"{base_url}/document/{bookmark['document_id']}")
    doc = doc_response.json()
    assert doc != None

    # regenerate document
    doc["status"] = "Done"
    new_doc_response = requests.post(f"{base_url}/document/", json=doc)
    assert new_doc_response.status_code == 202
    new_doc = new_doc_response.json()
    assert new_doc != None

    bookmark_response = requests.get(f"{base_url}/bookmark", params={"url": url})
    bookmark2 = bookmark_response.json()
    assert bookmark2["cloned_documents"] != None
    assert bookmark2["document_id"] != new_doc["id"]


def test_get_documents_plus_by_user_id():
    response = requests.get(f"{base_url}/documents_plus/user/777")
    assert response.status_code == 200
    documents_plus = response.json()
    assert len(documents_plus) > 0
