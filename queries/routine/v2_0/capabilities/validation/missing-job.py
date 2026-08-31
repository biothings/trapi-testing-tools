from tests import http

trapi_version = "2.0"
method = "GET"
endpoint = "/asyncquery_status/fakeID"
tests = [http.Status.expect(404)]
