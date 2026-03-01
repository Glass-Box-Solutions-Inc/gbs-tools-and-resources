"""
Comprehensive Test Suite for Yevrah Legal Research Terminal

Tests validate:
1. Dual search returns exactly 5 keyword + 5 semantic results
2. API queries formulated correctly
3. Jurisdiction codes mapped correctly per CourtListener spec
4. Date filters formatted and included correctly
5. Date parameters NOT added when no dates specified
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
import sys
import os

# Add project directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tools import map_jurisdiction_to_codes, parse_date_input
from courtlistener import CourtListenerClient


class TestJurisdictionMapping(unittest.TestCase):
    """Test jurisdiction code mapping against CourtListener API spec."""

    def test_federal_appellate_9th_circuit(self):
        """Test: '9th Circuit' → 'ca9'"""
        result = map_jurisdiction_to_codes("9th Circuit")
        self.assertTrue(result["valid"])
        self.assertIn("ca9", result["court_codes"])

    def test_federal_appellate_fifth_circuit(self):
        """Test: '5th Circuit' → 'ca5'"""
        result = map_jurisdiction_to_codes("5th Circuit")
        self.assertTrue(result["valid"])
        self.assertIn("ca5", result["court_codes"])

    def test_state_supreme_california(self):
        """Test: 'california' → includes 'cal' (state supreme court)"""
        result = map_jurisdiction_to_codes("california")
        self.assertTrue(result["valid"])
        self.assertIn("cal", result["court_codes"])

    def test_state_appellate_california(self):
        """Test: 'California Court of Appeal' → 'calctapp'"""
        result = map_jurisdiction_to_codes("California Court of Appeal")
        self.assertTrue(result["valid"])
        self.assertIn("calctapp", result["court_codes"])

    def test_state_courts_multiple(self):
        """Test: 'California state courts' → 'cal calctapp'"""
        result = map_jurisdiction_to_codes("California state courts")
        self.assertTrue(result["valid"])
        codes = result["court_codes"].split()
        self.assertIn("cal", codes)
        self.assertIn("calctapp", codes)

    def test_california_state(self):
        """Test: 'california state' → 'cal calctapp'"""
        result = map_jurisdiction_to_codes("california state")
        self.assertTrue(result["valid"])
        codes = result["court_codes"].split()
        self.assertIn("cal", codes)
        self.assertIn("calctapp", codes)

    def test_federal_district_northern_california(self):
        """Test: 'Northern District of California' → 'cand'"""
        result = map_jurisdiction_to_codes("Northern District of California")
        self.assertTrue(result["valid"])
        self.assertIn("cand", result["court_codes"])

    def test_pattern_state_of_texas(self):
        """Test: 'state of Texas' → Texas state courts"""
        result = map_jurisdiction_to_codes("state of Texas")
        self.assertTrue(result["valid"])
        codes = result["court_codes"].split()
        # Should include Texas supreme and appellate courts
        self.assertIn("tex", codes)

    def test_pattern_federal_courts_in_texas(self):
        """Test: 'federal courts in Texas' → Texas federal courts"""
        result = map_jurisdiction_to_codes("federal courts in Texas")
        self.assertTrue(result["valid"])
        codes = result["court_codes"].split()
        # Should include Texas federal district courts and 5th circuit
        self.assertTrue(any(code in ["txnd", "txed", "txsd", "txwd", "ca5"] for code in codes))

    def test_texas_federal(self):
        """Test: 'texas federal' → Texas federal courts"""
        result = map_jurisdiction_to_codes("texas federal")
        self.assertTrue(result["valid"])
        codes = result["court_codes"].split()
        # Should include Texas federal district courts
        self.assertTrue(any(code in ["txnd", "txed", "txsd", "txwd", "ca5"] for code in codes))

    def test_new_york_state(self):
        """Test: 'New York state' → New York state courts"""
        result = map_jurisdiction_to_codes("New York state")
        self.assertTrue(result["valid"])
        codes = result["court_codes"].split()
        self.assertIn("ny", codes)

    def test_empty_jurisdiction(self):
        """Test: Empty string returns no filter"""
        result = map_jurisdiction_to_codes("")
        self.assertTrue(result["valid"])
        self.assertEqual(result["court_codes"], "")
        self.assertIn("All courts", result["description"])

    def test_direct_court_codes(self):
        """Test: Direct court codes like 'ca9 cal' are accepted"""
        result = map_jurisdiction_to_codes("ca9 cal")
        self.assertTrue(result["valid"])
        self.assertEqual(result["court_codes"], "ca9 cal")

    def test_case_insensitive(self):
        """Test: Case variations work (CALIFORNIA, California, california)"""
        result1 = map_jurisdiction_to_codes("CALIFORNIA")
        result2 = map_jurisdiction_to_codes("California")
        result3 = map_jurisdiction_to_codes("california")

        self.assertTrue(result1["valid"])
        self.assertTrue(result2["valid"])
        self.assertTrue(result3["valid"])

        # All should return the same codes
        self.assertEqual(result1["court_codes"], result2["court_codes"])
        self.assertEqual(result2["court_codes"], result3["court_codes"])


class TestDateParsing(unittest.TestCase):
    """Test date filter parsing and formatting."""

    def test_empty_date(self):
        """Test: Empty string returns no date filter"""
        result = parse_date_input("")
        self.assertTrue(result["valid"])
        self.assertEqual(result["filed_after"], "")
        self.assertEqual(result["filed_before"], "")
        self.assertIn("All time", result["description"])

    def test_last_5_years(self):
        """Test: 'last 5 years' calculates correct date range"""
        result = parse_date_input("last 5 years")
        self.assertTrue(result["valid"])
        self.assertIsNotNone(result["filed_after"])
        self.assertIsNotNone(result["filed_before"])

        # Verify format is MM/DD/YYYY
        self.assertRegex(result["filed_after"], r'^\d{2}/\d{2}/\d{4}$')
        self.assertRegex(result["filed_before"], r'^\d{2}/\d{2}/\d{4}$')

        # Verify approximately 5 years ago
        today = datetime.now()
        five_years_ago = today - timedelta(days=5*365)
        self.assertEqual(result["filed_after"], five_years_ago.strftime("%m/%d/%Y"))

    def test_past_3_years(self):
        """Test: 'past 3 years' works the same as 'last 3 years'"""
        result = parse_date_input("past 3 years")
        self.assertTrue(result["valid"])
        self.assertRegex(result["filed_after"], r'^\d{2}/\d{2}/\d{4}$')

    def test_since_2020(self):
        """Test: 'since 2020' → filed_after parameter"""
        result = parse_date_input("since 2020")
        self.assertTrue(result["valid"])
        self.assertEqual(result["filed_after"], "01/01/2020")
        self.assertIsNotNone(result["filed_before"])

    def test_after_2020(self):
        """Test: 'after 2020' works same as 'since 2020'"""
        result = parse_date_input("after 2020")
        self.assertTrue(result["valid"])
        self.assertEqual(result["filed_after"], "01/01/2020")

    def test_from_2020(self):
        """Test: 'from 2020' works same as 'since 2020'"""
        result = parse_date_input("from 2020")
        self.assertTrue(result["valid"])
        self.assertEqual(result["filed_after"], "01/01/2020")

    def test_before_2020(self):
        """Test: 'before 2020' → filed_before parameter only"""
        result = parse_date_input("before 2020")
        self.assertTrue(result["valid"])
        self.assertEqual(result["filed_after"], "")
        self.assertEqual(result["filed_before"], "12/31/2020")

    def test_year_range_2020_to_2023(self):
        """Test: '2020 to 2023' → both parameters"""
        result = parse_date_input("2020 to 2023")
        self.assertTrue(result["valid"])
        self.assertEqual(result["filed_after"], "01/01/2020")
        self.assertEqual(result["filed_before"], "12/31/2023")

    def test_year_range_with_dash(self):
        """Test: '2020-2023' works same as '2020 to 2023'"""
        result = parse_date_input("2020-2023")
        self.assertTrue(result["valid"])
        self.assertEqual(result["filed_after"], "01/01/2020")
        self.assertEqual(result["filed_before"], "12/31/2023")

    def test_single_year(self):
        """Test: '2020' → full year range"""
        result = parse_date_input("2020")
        self.assertTrue(result["valid"])
        self.assertEqual(result["filed_after"], "01/01/2020")
        self.assertEqual(result["filed_before"], "12/31/2020")

    def test_iso_date_format(self):
        """Test: '2020-01-15' → '01/15/2020'"""
        result = parse_date_input("2020-01-15")
        self.assertTrue(result["valid"])
        self.assertEqual(result["filed_after"], "01/15/2020")

    def test_slash_date_format(self):
        """Test: '01/15/2020' stays as is"""
        result = parse_date_input("01/15/2020")
        self.assertTrue(result["valid"])
        self.assertEqual(result["filed_after"], "01/15/2020")

    def test_invalid_date(self):
        """Test: Invalid date format returns error"""
        result = parse_date_input("invalid date format")
        self.assertFalse(result["valid"])
        self.assertIn("Could not parse", result["description"])


class TestAPIParameterConstruction(unittest.TestCase):
    """Test CourtListener API parameter construction."""

    @patch.dict(os.environ, {'COURTLISTENER_API_KEY': 'test_key'})
    def setUp(self):
        """Set up test client."""
        self.client = CourtListenerClient()

    def test_basic_parameters(self):
        """Test: Basic query parameters are always included"""
        params = self.client._build_params(
            query="test query",
            search_type="keyword"
        )

        self.assertEqual(params["q"], "test query")
        self.assertEqual(params["type"], "o")  # opinions
        self.assertIn("page_size", params)
        self.assertIn("order_by", params)

    def test_semantic_flag_added_for_semantic_search(self):
        """Test: 'semantic' parameter only added for semantic search"""
        keyword_params = self.client._build_params(
            query="test",
            search_type="keyword"
        )
        semantic_params = self.client._build_params(
            query="test",
            search_type="semantic"
        )

        self.assertNotIn("semantic", keyword_params)
        self.assertEqual(semantic_params.get("semantic"), "true")

    def test_court_parameter_included_when_provided(self):
        """Test: Court codes included when provided"""
        params = self.client._build_params(
            query="test",
            search_type="keyword",
            court="ca9 cal"
        )

        self.assertEqual(params["court"], "ca9 cal")

    def test_court_parameter_not_included_when_empty(self):
        """Test: Court parameter NOT added when empty"""
        params = self.client._build_params(
            query="test",
            search_type="keyword",
            court=""
        )

        self.assertNotIn("court", params)

    def test_date_filters_included_when_provided(self):
        """Test: Date filters included when provided"""
        params = self.client._build_params(
            query="test",
            search_type="keyword",
            filed_after="01/01/2020",
            filed_before="12/31/2023"
        )

        self.assertEqual(params["filed_after"], "01/01/2020")
        self.assertEqual(params["filed_before"], "12/31/2023")

    def test_date_filters_not_included_when_empty(self):
        """Test: Date parameters NOT added when empty"""
        params = self.client._build_params(
            query="test",
            search_type="keyword",
            filed_after="",
            filed_before=""
        )

        self.assertNotIn("filed_after", params)
        self.assertNotIn("filed_before", params)

    def test_filed_after_only(self):
        """Test: Only filed_after added when filed_before empty"""
        params = self.client._build_params(
            query="test",
            search_type="keyword",
            filed_after="01/01/2020",
            filed_before=""
        )

        self.assertEqual(params["filed_after"], "01/01/2020")
        self.assertNotIn("filed_before", params)

    def test_filed_before_only(self):
        """Test: Only filed_before added when filed_after empty"""
        params = self.client._build_params(
            query="test",
            search_type="keyword",
            filed_after="",
            filed_before="12/31/2020"
        )

        self.assertNotIn("filed_after", params)
        self.assertEqual(params["filed_before"], "12/31/2020")

    def test_page_size_bounds(self):
        """Test: Page size bounded between 1 and 20"""
        params_too_small = self.client._build_params(
            query="test",
            search_type="keyword",
            page_size=0
        )
        params_too_large = self.client._build_params(
            query="test",
            search_type="keyword",
            page_size=100
        )

        self.assertEqual(params_too_small["page_size"], 1)
        self.assertEqual(params_too_large["page_size"], 20)

    def test_status_filter_published(self):
        """Test: Status filter for published opinions"""
        params = self.client._build_params(
            query="test",
            search_type="keyword",
            status="published"
        )

        self.assertEqual(params["stat_Published"], "on")
        self.assertNotIn("stat_Unpublished", params)

    def test_status_filter_unpublished(self):
        """Test: Status filter for unpublished opinions"""
        params = self.client._build_params(
            query="test",
            search_type="keyword",
            status="unpublished"
        )

        self.assertEqual(params["stat_Unpublished"], "on")
        self.assertNotIn("stat_Published", params)

    def test_status_filter_all(self):
        """Test: Status filter for all opinions"""
        params = self.client._build_params(
            query="test",
            search_type="keyword",
            status="all"
        )

        self.assertEqual(params["stat_Published"], "on")
        self.assertEqual(params["stat_Unpublished"], "on")

    def test_cursor_parameter(self):
        """Test: Cursor parameter for pagination"""
        params = self.client._build_params(
            query="test",
            search_type="keyword",
            cursor="next_page_token"
        )

        self.assertEqual(params["cursor"], "next_page_token")

    def test_highlight_parameter(self):
        """Test: Highlight parameter"""
        params_on = self.client._build_params(
            query="test",
            search_type="keyword",
            highlight=True
        )
        params_off = self.client._build_params(
            query="test",
            search_type="keyword",
            highlight=False
        )

        self.assertEqual(params_on["highlight"], "on")
        self.assertNotIn("highlight", params_off)


class TestDualSearchResults(unittest.TestCase):
    """Test dual search result handling."""

    @patch('reranker.CohereReranker')
    @patch('courtlistener.CourtListenerClient')
    def test_dual_search_returns_10_results(self, mock_client_class, mock_reranker_class):
        """Test: Dual search returns exactly 5 keyword + 5 semantic results"""
        # Import here to avoid early loading issues
        from tools import execute_search_case_law

        # Mock CourtListener API responses
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        # Create mock keyword results (10 cases)
        keyword_results = {
            "results": [{"case_name": f"Keyword Case {i}", "court": "ca9"} for i in range(10)],
            "_api_url": "http://test.com/keyword"
        }

        # Create mock semantic results (10 cases)
        semantic_results = {
            "results": [{"case_name": f"Semantic Case {i}", "court": "cal"} for i in range(10)],
            "_api_url": "http://test.com/semantic"
        }

        # Configure mock to return different results based on search_type
        def search_side_effect(*args, **kwargs):
            if kwargs.get('search_type') == 'keyword':
                return keyword_results
            else:
                return semantic_results

        mock_client.search.side_effect = search_side_effect

        # Mock Cohere reranker
        mock_reranker = MagicMock()
        mock_reranker.is_available.return_value = True

        # Reranker returns top 5 with rerank scores
        def rerank_side_effect(*args, **kwargs):
            docs = kwargs.get('documents', [])
            top_n = kwargs.get('top_n', 5)
            results = []
            for i, doc in enumerate(docs[:top_n]):
                result_doc = dict(doc)
                result_doc['rerank_score'] = 0.9 - (i * 0.1)
                results.append(result_doc)
            return results

        mock_reranker.rerank.side_effect = rerank_side_effect
        mock_reranker_class.return_value = mock_reranker

        # Execute dual search
        arguments = {
            "query": "test query",
            "search_type": "both"
        }
        result = execute_search_case_law(arguments, mock_client)

        # Verify we got exactly 10 results
        cases = result.get("results", [])
        self.assertEqual(len(cases), 10, f"Expected 10 results, got {len(cases)}")

        # Count results by source
        keyword_count = sum(1 for c in cases if c.get("_search_source") == "keyword")
        semantic_count = sum(1 for c in cases if c.get("_search_source") == "semantic")

        self.assertEqual(keyword_count, 5, f"Expected 5 keyword results, got {keyword_count}")
        self.assertEqual(semantic_count, 5, f"Expected 5 semantic results, got {semantic_count}")

    @patch('reranker.CohereReranker')
    @patch('courtlistener.CourtListenerClient')
    def test_keyword_results_tagged_correctly(self, mock_client_class, mock_reranker_class):
        """Test: Keyword results tagged with _search_source: 'keyword'"""
        from tools import execute_search_case_law

        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        keyword_results = {
            "results": [{"case_name": f"Case {i}"} for i in range(10)],
            "_api_url": "http://test.com"
        }
        semantic_results = {
            "results": [{"case_name": f"Semantic {i}"} for i in range(10)],
            "_api_url": "http://test.com"
        }

        def search_side_effect(*args, **kwargs):
            if kwargs.get('search_type') == 'keyword':
                return keyword_results
            else:
                return semantic_results

        mock_client.search.side_effect = search_side_effect

        mock_reranker = MagicMock()
        mock_reranker.is_available.return_value = True
        mock_reranker.rerank.return_value = [
            {**doc, "rerank_score": 0.9} for doc in semantic_results["results"][:5]
        ]
        mock_reranker_class.return_value = mock_reranker

        arguments = {"query": "test", "search_type": "both"}
        result = execute_search_case_law(arguments, mock_client)

        # Verify all keyword results have correct tag
        cases = result.get("results", [])
        keyword_cases = [c for c in cases if c.get("_search_source") == "keyword"]

        self.assertEqual(len(keyword_cases), 5)
        for case in keyword_cases:
            self.assertEqual(case["_search_source"], "keyword")

    @patch('reranker.CohereReranker')
    @patch('courtlistener.CourtListenerClient')
    def test_semantic_results_tagged_correctly(self, mock_client_class, mock_reranker_class):
        """Test: Semantic results tagged with _search_source: 'semantic'"""
        from tools import execute_search_case_law

        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        keyword_results = {
            "results": [{"case_name": f"Case {i}"} for i in range(10)],
            "_api_url": "http://test.com"
        }
        semantic_results = {
            "results": [{"case_name": f"Semantic {i}"} for i in range(10)],
            "_api_url": "http://test.com"
        }

        def search_side_effect(*args, **kwargs):
            if kwargs.get('search_type') == 'keyword':
                return keyword_results
            else:
                return semantic_results

        mock_client.search.side_effect = search_side_effect

        mock_reranker = MagicMock()
        mock_reranker.is_available.return_value = True
        mock_reranker.rerank.return_value = [
            {**doc, "rerank_score": 0.9} for doc in semantic_results["results"][:5]
        ]
        mock_reranker_class.return_value = mock_reranker

        arguments = {"query": "test", "search_type": "both"}
        result = execute_search_case_law(arguments, mock_client)

        # Verify all semantic results have correct tag
        cases = result.get("results", [])
        semantic_cases = [c for c in cases if c.get("_search_source") == "semantic"]

        self.assertEqual(len(semantic_cases), 5)
        for case in semantic_cases:
            self.assertEqual(case["_search_source"], "semantic")


def run_tests():
    """Run all tests and display results."""
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Add all test cases
    suite.addTests(loader.loadTestsFromTestCase(TestJurisdictionMapping))
    suite.addTests(loader.loadTestsFromTestCase(TestDateParsing))
    suite.addTests(loader.loadTestsFromTestCase(TestAPIParameterConstruction))
    suite.addTests(loader.loadTestsFromTestCase(TestDualSearchResults))

    # Run tests with verbose output
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # Print summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    print(f"Tests run: {result.testsRun}")
    print(f"Successes: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print("="*70)

    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
