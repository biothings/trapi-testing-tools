from tests import http

method = "GET"
endpoint = "/asyncquery_status/fakeID"
tests = [http.Status.expect(404)]
