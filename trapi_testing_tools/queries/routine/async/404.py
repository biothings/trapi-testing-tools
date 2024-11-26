from trapi_testing_tools.tests import http

method = "GET"
endpoint = "/asyncquery_status/fakeID"
tests = [http.status(404)]
