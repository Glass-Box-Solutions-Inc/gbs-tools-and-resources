"""
Tests for AI Q&A Handler
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from hitl.ai_qa_handler import AIQAHandler


@pytest.fixture
def mock_context_manager():
    """Mock ChannelContextManager"""
    manager = Mock()
    manager.get_channel_context.return_value = Mock(
        project_name='test-project',
        description='Test project description',
        active_tasks=[
            {'task_id': 'task-123', 'goal': 'Test goal 1', 'state': 'RUNNING', 'created_at': '2026-01-01'},
            {'task_id': 'task-456', 'goal': 'Test goal 2', 'state': 'RUNNING', 'created_at': '2026-01-01'},
        ],
        recent_messages=[
            {'user': 'U123', 'text': 'Test message 1'},
            {'user': 'U456', 'text': 'Test message 2'}
        ]
    )
    return manager


@pytest.fixture
def mock_task_store():
    """Mock TaskStore"""
    store = Mock()
    store.db_path = '/tmp/test.db'
    return store


@pytest.fixture
def mock_human_router():
    """Mock HumanRouter"""
    router = Mock()
    router.escalate = AsyncMock()
    return router


@pytest.fixture
def ai_handler(mock_context_manager, mock_task_store, mock_human_router):
    """Create AIQAHandler instance with mocks"""
    with patch('hitl.ai_qa_handler.genai'):
        handler = AIQAHandler(
            gemini_api_key='test_api_key',
            context_manager=mock_context_manager,
            task_store=mock_task_store,
            human_router=mock_human_router,
            confidence_threshold=0.6
        )
        # Mock model
        handler.model = Mock()
        handler.model.generate_content = Mock()
        return handler


class TestAIQAHandler:
    """Test cases for AIQAHandler"""
    
    def test_initialization(self, ai_handler):
        """Test handler initializes correctly"""
        assert ai_handler.confidence_threshold == 0.6
        assert ai_handler.timeout_seconds == 10
        assert ai_handler.context_manager is not None
    
    def test_should_auto_escalate_billing(self, ai_handler):
        """Test billing keywords trigger auto-escalation"""
        assert ai_handler._should_auto_escalate("What is the billing for this month?")
        assert ai_handler._should_auto_escalate("How much does this cost?")
        assert ai_handler._should_auto_escalate("Can I see my invoice?")
    
    def test_should_not_auto_escalate_normal(self, ai_handler):
        """Test normal questions don't auto-escalate"""
        assert not ai_handler._should_auto_escalate("What is task-123 doing?")
        assert not ai_handler._should_auto_escalate("How many tasks are running?")
    
    def test_build_context_with_channel(self, ai_handler, mock_context_manager):
        """Test context building from channel"""
        context = ai_handler._build_context('C123', 'test-project')
        
        assert context['project_name'] == 'test-project'
        assert context['project_description'] == 'Test project description'
        assert len(context['active_tasks']) == 2
        assert len(context['recent_messages']) == 2
    
    def test_build_context_without_channel(self, ai_handler):
        """Test context building without channel"""
        context = ai_handler._build_context(None, 'test-project')
        
        assert context['project_name'] == 'test-project'
        assert context['project_description'] == ''
    
    def test_extract_confidence_high(self, ai_handler):
        """Test high confidence extraction"""
        response = "Task task-123 is currently running and has completed 5 steps."
        confidence = ai_handler._extract_confidence(response)
        
        assert confidence == 0.9
    
    def test_extract_confidence_low(self, ai_handler):
        """Test low confidence extraction"""
        response = "I don't know the answer to that question."
        confidence = ai_handler._extract_confidence(response)
        
        assert confidence == 0.3
    
    def test_extract_confidence_escalate(self, ai_handler):
        """Test escalation marker confidence"""
        response = "ESCALATE: This requires human assistance."
        confidence = ai_handler._extract_confidence(response)
        
        assert confidence == 0.1
    
    def test_should_escalate_low_confidence(self, ai_handler):
        """Test escalation based on low confidence"""
        assert ai_handler._should_escalate("Some response", 0.4)
        assert not ai_handler._should_escalate("Some response", 0.8)
    
    def test_should_escalate_marker(self, ai_handler):
        """Test escalation based on marker in response"""
        assert ai_handler._should_escalate("ESCALATE: Need help", 0.9)
        assert ai_handler._should_escalate("This requires human assistance", 0.9)
    
    def test_filter_pii_email(self, ai_handler):
        """Test PII filtering for emails"""
        text = "My email is test@example.com"
        filtered = ai_handler._filter_pii(text)
        
        assert 'test@example.com' not in filtered
        assert '[EMAIL_REDACTED]' in filtered
    
    def test_filter_pii_phone(self, ai_handler):
        """Test PII filtering for phone numbers"""
        text = "Call me at 123-456-7890"
        filtered = ai_handler._filter_pii(text)
        
        assert '123-456-7890' not in filtered
        assert '[PHONE_REDACTED]' in filtered
    
    def test_filter_pii_ssn(self, ai_handler):
        """Test PII filtering for SSNs"""
        text = "My SSN is 123-45-6789"
        filtered = ai_handler._filter_pii(text)
        
        assert '123-45-6789' not in filtered
        assert '[SSN_REDACTED]' in filtered
    
    def test_build_prompt(self, ai_handler):
        """Test prompt building"""
        context = {
            'project_name': 'test-project',
            'project_description': 'Test description',
            'active_tasks': [
                {'task_id': 'task-123', 'goal': 'Test goal', 'state': 'RUNNING'}
            ],
            'recent_messages': []
        }
        
        prompt = ai_handler._build_prompt("What is task-123 doing?", context)
        
        assert 'test-project' in prompt
        assert 'task-123' in prompt
        assert 'What is task-123 doing?' in prompt
    
    @pytest.mark.asyncio
    async def test_answer_question_auto_escalate(self, ai_handler, mock_human_router):
        """Test question with billing keyword auto-escalates"""
        response = await ai_handler.answer_question(
            "What is the cost?",
            user_id='U123',
            channel_id='C123',
            project_name='test-project'
        )
        
        assert "escalated" in response.lower()
        mock_human_router.escalate.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_answer_question_success(self, ai_handler):
        """Test successful question answering"""
        # Mock Gemini response
        mock_response = Mock()
        mock_response.text = "Task task-123 is running successfully."
        ai_handler.model.generate_content.return_value = mock_response
        
        response = await ai_handler.answer_question(
            "What is task-123 doing?",
            user_id='U123',
            channel_id='C123',
            project_name='test-project'
        )
        
        assert "running successfully" in response
    
    @pytest.mark.asyncio
    async def test_answer_question_escalate_low_confidence(
        self, ai_handler, mock_human_router
    ):
        """Test low confidence answer escalates"""
        # Mock low-confidence response
        mock_response = Mock()
        mock_response.text = "I don't know the answer."
        ai_handler.model.generate_content.return_value = mock_response
        
        response = await ai_handler.answer_question(
            "Complex question?",
            user_id='U123',
            channel_id='C123',
            project_name='test-project'
        )
        
        assert "escalated" in response.lower()
        mock_human_router.escalate.assert_called_once()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
