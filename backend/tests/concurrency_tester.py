import time
import requests


def call_url(url):
    count = 0
    while True:
        start_time = time.time()
        response = requests.get(url)
        elapsed_time = time.time() - start_time
        print(
            f"Elapsed time: {elapsed_time} seconds. Status code: {response.status_code}"
        )
        time.sleep(0.5)
        count += 1
        if count == 200:
            break


if __name__ == "__main__":
    call_url("http://localhost:8889/document_plus/55")
