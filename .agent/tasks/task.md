List all all tasks that need to be done for this project.

Order of priority:
1. [x] Move prompts from research_graph.py to the database. It's important the the code will fail, if there is no DB prompts. That will help us to catch the issue early.
2. When deleting a bookmark, we should also delete the associated document and all related chats. See the following logs that shows the issue, the delete bookmark API, the creation of a new bookmark, and the previous chat being returned. Notice the chat session id is 320 before and after the deletion and creation of the bookmark.

    ```INFO:     127.0.0.1:56202 - "GET /api/v1/chat/sessions/320/messages HTTP/1.1" 200 OK
    2026-02-04 16:32:55 - security_middleware.py - 279 - INFO - REQUEST: {'timestamp': '2026-02-04T21:32:55.464726', 'method': 'GET', 'url': 'http://localhost:8000/bookmarks/119', 'client_ip': '127.0.0.1', 'firebase_uid': None, 'status_code': 200, 'duration_ms': 128.87, 'user_agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36'}
    INFO:     127.0.0.1:56203 - "GET /bookmarks/119 HTTP/1.1" 200 OK
    2026-02-04 16:32:55 - firebase_auth.py - 86 - INFO - Successfully verified token for user: HqAXhad3jrUWmPibnMf1xZczNIq2
    2026-02-04 16:32:55 - user_context.py - 94 - INFO - Successfully verified Firebase token for user: HqAXhad3jrUWmPibnMf1xZczNIq2
    2026-02-04 16:32:55 - security_middleware.py - 279 - INFO - REQUEST: {'timestamp': '2026-02-04T21:32:55.510138', 'method': 'GET', 'url': 'http://localhost:8000/documents/109', 'client_ip': '127.0.0.1', 'firebase_uid': None, 'status_code': 200, 'duration_ms': 34.07, 'user_agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36'}

    INFO:     127.0.0.1:56243 - "DELETE /bookmarks/119 HTTP/1.1" 200 OK
    2026-02-04 16:33:08 - firebase_auth.py - 86 - INFO - Successfully verified token for user: HqAXhad3jrUWmPibnMf1xZczNIq2
    2026-02-04 16:33:08 - user_context.py - 94 - INFO - Successfully verified Firebase token for user: HqAXhad3jrUWmPibnMf1xZczNIq2
    2026-02-04 16:33:08 - bookmarks.py - 817 - INFO - Creating bookmark for URL: https://www.linkedin.com/feed/update/urn:li:activity:7424802685998247936/
    2026-02-04 16:33:08 - bookmarks.py - 977 - INFO - Document exists for URL https://www.linkedin.com/feed/update/urn:li:activity:7424802685998247936/ but no bookmark, creating bookmark linked to document 109
    2026-02-04 16:33:08 - notifications.py - 70 - INFO - Sending document_ready notification to user HqAXhad3jrUWmPibnMf1xZczNIq2 (1 connections)
    2026-02-04 16:33:08 - bookmarks.py - 83 - INFO - Sent document_ready notification for document 109 to user HqAXhad3jrUWmPibnMf1xZczNIq2
    2026-02-04 16:33:08 - security_middleware.py - 279 - INFO - REQUEST: {'timestamp': '2026-02-04T21:33:08.297673', 'method': 'POST', 'url': 'http://localhost:8000/bookmarks/', 'client_ip': '127.0.0.1', 'firebase_uid': None, 'status_code': 201, 'duration_ms': 100.29, 'user_agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36'}
    INFO:     127.0.0.1:56243 - "POST /bookmarks/ HTTP/1.1" 201 Created
    2026-02-04 16:33:08 - firebase_auth.py - 86 - INFO - Successfully verified token for user: HqAXhad3jrUWmPibnMf1xZczNIq2
    2026-02-04 16:33:08 - user_context.py - 94 - INFO - Successfully verified Firebase token for user: HqAXhad3jrUWmPibnMf1xZczNIq2
    2026-02-04 16:33:08 - security_middleware.py - 279 - INFO - REQUEST: {'timestamp': '2026-02-04T21:33:08.321879', 'method': 'GET', 'url': 'http://localhost:8000/api/v1/chat/sessions/320/messages', 'client_ip': '127.0.0.1', 'firebase_uid': None, 'status_code': 200, 'duration_ms': 9.47, 'user_agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36'}
    INFO:     127.0.0.1:56243 - "GET /api/v1/chat/sessions/320/messages HTTP/1.1" 200 OK```

 