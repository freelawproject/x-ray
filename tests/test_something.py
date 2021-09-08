from unittest import TestCase


class DataTest(TestCase):
    """Obey the testing goat."""

    def test_something(self):
        """
        A testing template -- make to update tests.yml if you change the
        testing name.
        """

        matches = True
        expected_matches = True

        self.assertEqual(matches, expected_matches)
