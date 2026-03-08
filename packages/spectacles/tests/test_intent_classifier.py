"""
Tests for Intent Classifier
"""

import pytest
from hitl.intent_classifier import IntentClassifier, Intent


@pytest.fixture
def classifier():
    """Create IntentClassifier instance"""
    return IntentClassifier(use_ai_fallback=False)


class TestIntentClassifier:
    """Test cases for IntentClassifier"""
    
    def test_initialization(self, classifier):
        """Test classifier initializes correctly"""
        assert classifier.use_ai_fallback == False
        assert classifier.ai_confidence_threshold == 0.6
    
    def test_classify_help(self, classifier):
        """Test help intent classification"""
        result = classifier.classify('help')
        assert result.intent == Intent.HELP
        assert result.confidence >= 0.7
    
    def test_classify_status_query(self, classifier):
        """Test status query classification"""
        result = classifier.classify('status of task-123')
        assert result.intent == Intent.STATUS_QUERY
        assert 'task-123' in result.extracted_data.get('task_id', '')
    
    def test_classify_command(self, classifier):
        """Test command classification"""
        result = classifier.classify('pause task-456')
        assert result.intent == Intent.COMMAND
        assert result.extracted_data.get('command') in ['pause', 'status']
    
    def test_classify_channel_create(self, classifier):
        """Test channel creation classification"""
        result = classifier.classify('create channel for glassy')
        assert result.intent == Intent.CHANNEL_CREATE
        assert result.extracted_data.get('project_name') == 'glassy'
    
    def test_classify_question(self, classifier):
        """Test question classification"""
        result = classifier.classify('What is happening?')
        assert result.intent == Intent.QUESTION
    
    def test_classify_empty(self, classifier):
        """Test empty message classification"""
        result = classifier.classify('')
        assert result.intent == Intent.HELP
    
    def test_extract_task_id(self, classifier):
        """Test task ID extraction"""
        result = classifier.classify('What is task 789 doing?')
        assert result.extracted_data.get('task_id') == 'task-789'
    
    def test_extract_command(self, classifier):
        """Test command extraction"""
        assert classifier._extract_command('pause the task') == 'pause'
        assert classifier._extract_command('cancel it') == 'cancel'
        assert classifier._extract_command('list all tasks') == 'list'
    
    def test_extract_project_name(self, classifier):
        """Test project name extraction"""
        assert classifier._extract_project_name('create channel for glassy-v2') == 'glassy-v2'
        assert classifier._extract_project_name('new channel: test-project') == 'test-project'

    def test_help_intent_variations(self, classifier):
        """Test HELP intent with natural language variations (target: 90%+)"""
        help_cases = [
            # Core
            ("help", Intent.HELP),
            ("commands", Intent.HELP),

            # What can you do
            ("what can you do", Intent.HELP),
            ("what can spectacles do", Intent.HELP),
            ("what can this do?", Intent.HELP),
            ("what can the bot do", Intent.HELP),

            # How to use
            ("how do i use this", Intent.HELP),
            ("how can i use spectacles", Intent.HELP),
            ("how to work with this?", Intent.HELP),
            ("how does this work", Intent.HELP),
            ("how does spectacles work?", Intent.HELP),

            # Show/list variations
            ("show me commands", Intent.HELP),
            ("list commands", Intent.HELP),
            ("tell me the options", Intent.HELP),
            ("show me what you can do", Intent.HELP),

            # Available
            ("available commands", Intent.HELP),
            ("available options?", Intent.HELP),

            # Contractions
            ("what's available", Intent.HELP),
            ("what's possible", Intent.HELP),

            # Natural language
            ("i need help", Intent.HELP),
            ("help me out", Intent.HELP),
            ("help me get started", Intent.HELP),
        ]

        passed = 0
        failed_cases = []
        for message, expected_intent in help_cases:
            result = classifier.classify(message)
            if result.intent == expected_intent and result.confidence >= 0.75:
                passed += 1
            else:
                failed_cases.append(f"'{message}' → {result.intent} ({result.confidence:.2f})")

        accuracy = passed / len(help_cases)
        assert accuracy >= 0.9, f"HELP accuracy {accuracy:.0%} < 90%. Failed: {failed_cases}"

    def test_question_intent_variations(self, classifier):
        """Test QUESTION intent with contractions and mid-sentence (target: 90%+)"""
        question_cases = [
            # Start-anchored
            ("what is the current status", Intent.QUESTION),
            ("how does this work", Intent.QUESTION),
            ("why is it failing", Intent.QUESTION),

            # Contractions
            ("what's the status", Intent.QUESTION),
            ("where's my task", Intent.QUESTION),
            ("how's it going", Intent.QUESTION),
            ("when's it done", Intent.QUESTION),

            # Mid-sentence questions
            ("tell me about the project", Intent.QUESTION),
            ("explain what happened", Intent.QUESTION),
            ("show me what you found", Intent.QUESTION),

            # Information requests
            ("what is the task id", Intent.QUESTION),
            ("what are the results", Intent.QUESTION),
            ("do you know the url", Intent.QUESTION),
            ("do you have screenshots", Intent.QUESTION),

            # Helper verbs
            ("can you tell me the status", Intent.QUESTION),
            ("could you show me progress", Intent.QUESTION),
            ("would you explain this", Intent.QUESTION),

            # Question mark fallback
            ("is this working?", Intent.QUESTION),
            ("task complete?", Intent.QUESTION),
        ]

        passed = 0
        failed_cases = []
        for message, expected_intent in question_cases:
            result = classifier.classify(message)
            if result.intent == expected_intent and result.confidence >= 0.75:
                passed += 1
            else:
                failed_cases.append(f"'{message}' → {result.intent} ({result.confidence:.2f})")

        accuracy = passed / len(question_cases)
        assert accuracy >= 0.9, f"QUESTION accuracy {accuracy:.0%} < 90%. Failed: {failed_cases}"

    def test_priority_conflicts(self, classifier):
        """Test that QUESTION beats STATUS_QUERY when question words present"""
        conflict_cases = [
            # Should be QUESTION (has question words)
            ("what is the status", Intent.QUESTION),
            ("what's the current progress", Intent.QUESTION),
            ("how's the status", Intent.QUESTION),
            ("tell me the status", Intent.QUESTION),

            # Should be STATUS_QUERY (no question words)
            ("show status", Intent.STATUS_QUERY),
            ("status of task-123", Intent.STATUS_QUERY),
            ("current progress", Intent.STATUS_QUERY),
        ]

        for message, expected_intent in conflict_cases:
            result = classifier.classify(message)
            assert result.intent == expected_intent, \
                f"'{message}' misclassified as {result.intent}, expected {expected_intent}"

    def test_accuracy_thresholds(self, classifier):
        """Validate both HELP and QUESTION meet 90% accuracy threshold"""

        # HELP test set (10 messages)
        help_test_set = [
            "help", "commands", "what can you do", "show me commands",
            "how do i use this", "available options", "what's available",
            "i need help", "help me out", "how does this work"
        ]

        # QUESTION test set (10 messages)
        question_test_set = [
            "what is the status", "how does it work", "can you help",
            "what's the progress", "tell me about this", "show me what happened",
            "what are the results", "do you know", "is this working?", "why is it failing"
        ]

        # Test HELP accuracy
        help_correct = sum(
            1 for msg in help_test_set
            if classifier.classify(msg).intent == Intent.HELP
        )
        help_accuracy = help_correct / len(help_test_set)
        assert help_accuracy >= 0.9, f"HELP accuracy {help_accuracy:.0%} below 90%"

        # Test QUESTION accuracy
        question_correct = sum(
            1 for msg in question_test_set
            if classifier.classify(msg).intent == Intent.QUESTION
        )
        question_accuracy = question_correct / len(question_test_set)
        assert question_accuracy >= 0.9, f"QUESTION accuracy {question_accuracy:.0%} below 90%"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
