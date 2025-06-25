#!/usr/bin/python3
"""HRMWARE Tracker API - Tests"""

import unittest


class TestResponse(unittest.TestCase):
    """Test cases to check if we get the proper response(s)"""

    def test_response(self):
        self.assertEqual("foo".upper(), "FOO")


if __name__ == "__main__":
    unittest.main()
