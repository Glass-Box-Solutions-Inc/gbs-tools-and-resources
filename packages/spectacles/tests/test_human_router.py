"""
Tests for Human Router
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from hitl.human_router import HumanRouter


@pytest.fixture
def mock_slack_client():
    """Mock Slack client"""
    client = Mock()
    client.client = Mock()
    client.client.conversations_open = AsyncMock(return_value={'channel': {'id': 'D123'}})
    client.client.chat_postMessage = AsyncMock()
    return client


@pytest.fixture
def mock_context_manager():
    """Mock ChannelContextManager"""
    manager = Mock()
    manager.get_channels_by_project.return_value = ['C123']
    manager.get_mapping.return_value = Mock(
        project_name='test-project',
        owner='alex',
        description='Test project'
    )
    return manager


@pytest.fixture
def human_router(mock_slack_client, mock_context_manager):
    """Create HumanRouter instance with mocks"""
    router = HumanRouter(
        slack_client=mock_slack_client,
        context_manager=mock_context_manager,
        default_recipient='alex',
        recipient_map={
            'alex': 'U_ALEX',
            'brian': 'U_BRIAN'
        }
    )
    return router


class TestHumanRouter:
    """Test cases for HumanRouter"""
    
    def test_initialization(self, human_router):
        """Test router initializes correctly"""
        assert human_router.default_recipient == 'alex'
        assert 'alex' in human_router.recipients
        assert 'brian' in human_router.recipients
    
    def test_determine_recipient_billing(self, human_router):
        """Test billing keyword routes to alex"""
        recipient = human_router._determine_recipient(
            'test-project',
            'What is the billing for this month?'
        )
        assert recipient == 'alex'
    
    def test_determine_recipient_usage(self, human_router):
        """Test usage keyword routes to brian"""
        recipient = human_router._determine_recipient(
            'test-project',
            'What is my usage quota?'
        )
        assert recipient == 'brian'
    
    def test_determine_recipient_project_owner(self, human_router, mock_context_manager):
        """Test project owner routing"""
        recipient = human_router._determine_recipient(
            'test-project',
            'General question'
        )
        # Should route to alex (project owner from mock)
        assert recipient == 'alex'
    
    def test_determine_recipient_default(self, human_router):
        """Test default recipient fallback"""
        recipient = human_router._determine_recipient(
            None,
            'Random question'
        )
        assert recipient == 'alex'  # Default
    
    def test_format_escalation_message_basic(self, human_router):
        """Test basic escalation message formatting"""
        message = human_router._format_escalation_message(
            question='Test question?',
            user_id='U123',
            channel_id='C123',
            project_name='test-project',
            context={}
        )
        
        assert '🆘' in message
        assert 'Test question?' in message
        assert '<@U123>' in message
        assert 'test-project' in message
    
    def test_format_escalation_message_with_ai_response(self, human_router):
        """Test message with AI response"""
        message = human_router._format_escalation_message(
            question='Test question?',
            user_id='U123',
            channel_id='C123',
            project_name='test-project',
            context={},
            ai_response='AI attempted answer',
            confidence=0.4
        )
        
        assert 'AI attempted answer' in message
        assert 'confidence: 40%' in message
    
    def test_format_escalation_message_with_tasks(self, human_router):
        """Test message with active tasks"""
        context = {
            'active_tasks': [
                {'task_id': 'task-123', 'goal': 'Test goal 1', 'state': 'RUNNING'},
                {'task_id': 'task-456', 'goal': 'Test goal 2', 'state': 'AWAITING_HUMAN'}
            ]
        }
        
        message = human_router._format_escalation_message(
            question='Test question?',
            user_id='U123',
            channel_id='C123',
            project_name='test-project',
            context=context
        )
        
        assert 'task-123' in message
        assert 'task-456' in message
        assert 'RUNNING' in message
    
    def test_format_escalation_message_with_messages(self, human_router):
        """Test message with recent messages"""
        context = {
            'recent_messages': [
                {'user': 'U_ALICE', 'text': 'Message 1'},
                {'user': 'U_BOB', 'text': 'Message 2'}
            ]
        }
        
        message = human_router._format_escalation_message(
            question='Test question?',
            user_id='U123',
            channel_id='C123',
            project_name='test-project',
            context=context
        )
        
        assert 'Recent Messages' in message
        assert 'Message 1' in message
        assert 'Message 2' in message
    
    @pytest.mark.asyncio
    async def test_send_dm_success(self, human_router, mock_slack_client):
        """Test successful DM sending"""
        await human_router._send_dm('U_ALEX', 'Test message')
        
        mock_slack_client.client.conversations_open.assert_called_once_with(
            users='U_ALEX'
        )
        mock_slack_client.client.chat_postMessage.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_send_dm_failure(self, human_router, mock_slack_client):
        """Test DM failure handling"""
        mock_slack_client.client.conversations_open.side_effect = Exception("Slack error")
        
        with pytest.raises(Exception):
            await human_router._send_dm('U_ALEX', 'Test message')
    
    @pytest.mark.asyncio
    async def test_escalate_success(self, human_router, mock_slack_client):
        """Test successful escalation"""
        context = {
            'project_name': 'test-project',
            'active_tasks': [],
            'recent_messages': []
        }
        
        await human_router.escalate(
            question='Test question?',
            user_id='U123',
            channel_id='C123',
            context=context
        )
        
        # Should send DM
        mock_slack_client.client.chat_postMessage.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_escalate_with_fallback(self, human_router, mock_slack_client):
        """Test escalation with fallback on failure"""
        # First call fails, fallback should be tried
        mock_slack_client.client.conversations_open.side_effect = [
            Exception("First failed"),
            {'channel': {'id': 'D456'}}  # Fallback succeeds
        ]
        mock_slack_client.client.chat_postMessage = AsyncMock()
        
        context = {
            'project_name': 'test-project',
            'active_tasks': [],
            'recent_messages': []
        }
        
        # Route to brian first (usage keyword), should fallback to alex
        await human_router.escalate(
            question='What is my usage?',
            user_id='U123',
            channel_id='C123',
            context=context
        )
        
        # Should try brian first, then fallback
        assert mock_slack_client.client.conversations_open.call_count == 2
    
    def test_set_recipient(self, human_router):
        """Test setting recipient mapping"""
        human_router.set_recipient('charlie', 'U_CHARLIE')
        
        assert 'charlie' in human_router.recipients
        assert human_router.recipients['charlie'] == 'U_CHARLIE'
    
    def test_set_default_recipient(self, human_router):
        """Test setting default recipient"""
        human_router.set_default_recipient('brian')
        
        assert human_router.default_recipient == 'brian'
    
    def test_set_default_recipient_invalid(self, human_router):
        """Test setting invalid default recipient"""
        with pytest.raises(ValueError):
            human_router.set_default_recipient('nonexistent')


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
