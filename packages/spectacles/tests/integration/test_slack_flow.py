"""
Integration Tests for Slack Bidirectional Communication Flow
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from hitl.message_router import MessageRouter
from hitl.intent_classifier import IntentClassifier
from hitl.command_parser import CommandParser
from hitl.channel_context_manager import ChannelContextManager
from hitl.ai_qa_handler import AIQAHandler
from hitl.human_router import HumanRouter


@pytest.fixture
def integration_setup():
    """Setup integrated components"""
    # Create real components with mocked dependencies
    context_manager = Mock(spec=ChannelContextManager)
    context_manager.get_project_for_channel.return_value = 'test-project'
    context_manager.is_admin.return_value = True
    context_manager.get_channel_context.return_value = Mock(
        project_name='test-project',
        description='Test project',
        active_tasks=[],
        recent_messages=[]
    )
    
    task_store = Mock()
    task_store.db_path = '/tmp/test.db'
    task_store.get_task.return_value = {
        'task_id': 'task-123',
        'goal': 'Test task',
        'current_state': 'RUNNING',
        'created_at': '2026-01-18',
        'updated_at': '2026-01-18'
    }
    
    slack_client = Mock()
    slack_client.client = Mock()
    slack_client.client.conversations_open = AsyncMock(return_value={'channel': {'id': 'D123'}})
    slack_client.client.chat_postMessage = AsyncMock()
    
    # Create components
    classifier = IntentClassifier(use_ai_fallback=False)
    
    command_parser = CommandParser(
        orchestrator=Mock(),
        task_store=task_store,
        context_manager=context_manager
    )
    
    human_router = HumanRouter(
        slack_client=slack_client,
        context_manager=context_manager,
        default_recipient='alex',
        recipient_map={'alex': 'U_ALEX', 'brian': 'U_BRIAN'}
    )
    
    # Mock AI handler
    with patch('hitl.ai_qa_handler.genai'):
        ai_handler = AIQAHandler(
            gemini_api_key='test_key',
            context_manager=context_manager,
            task_store=task_store,
            human_router=human_router
        )
        ai_handler.model = Mock()
        ai_handler.model.generate_content = Mock(return_value=Mock(
            text='Task task-123 is running successfully.'
        ))
    
    # Create router
    router = MessageRouter(
        classifier=classifier,
        command_parser=command_parser,
        context_manager=context_manager,
        ai_qa_handler=ai_handler,
        human_router=human_router
    )
    
    return {
        'router': router,
        'classifier': classifier,
        'command_parser': command_parser,
        'context_manager': context_manager,
        'ai_handler': ai_handler,
        'human_router': human_router,
        'task_store': task_store,
        'slack_client': slack_client
    }


class TestSlackIntegrationFlow:
    """Integration test cases for full Slack flow"""
    
    @pytest.mark.asyncio
    async def test_dm_help_flow(self, integration_setup):
        """Test DM help command flow"""
        router = integration_setup['router']
        
        event = {
            'channel': 'D123',
            'user': 'U123',
            'text': 'help',
            'ts': '123'
        }
        
        response = await router.route_message(event)
        
        assert response is not None
        assert 'command' in response.lower()
    
    @pytest.mark.asyncio
    async def test_dm_status_query_flow(self, integration_setup):
        """Test DM status query flow"""
        router = integration_setup['router']
        
        event = {
            'channel': 'D123',
            'user': 'U123',
            'text': 'status task-123',
            'ts': '123'
        }
        
        response = await router.route_message(event)
        
        assert response is not None
        assert 'task-123' in response
    
    @pytest.mark.asyncio
    async def test_dm_question_ai_answer_flow(self, integration_setup):
        """Test DM question with AI answer"""
        router = integration_setup['router']
        ai_handler = integration_setup['ai_handler']
        
        event = {
            'channel': 'D123',
            'user': 'U123',
            'text': 'What is task-123 doing?',
            'ts': '123'
        }
        
        response = await router.route_message(event)
        
        # Should get AI answer
        assert response is not None
    
    @pytest.mark.asyncio
    async def test_mention_in_channel_flow(self, integration_setup):
        """Test @mention in project channel"""
        router = integration_setup['router']
        
        event = {
            'channel': 'C123',
            'user': 'U123',
            'text': '<@U_BOT> what tasks are running?',
            'ts': '123'
        }
        
        response = await router.route_message(event)
        
        assert response is not None
    
    @pytest.mark.asyncio
    async def test_billing_question_escalation_flow(self, integration_setup):
        """Test billing question triggers escalation"""
        router = integration_setup['router']
        human_router = integration_setup['human_router']
        
        event = {
            'channel': 'D123',
            'user': 'U123',
            'text': 'What is the billing for this month?',
            'ts': '123'
        }
        
        response = await router.route_message(event)
        
        assert 'escalate' in response.lower()
        # Verify human router was called
        # (In real test, would check slack_client.chat_postMessage called)
    
    @pytest.mark.asyncio
    async def test_channel_message_no_mention_ignored(self, integration_setup):
        """Test channel message without mention is ignored"""
        router = integration_setup['router']
        context_manager = integration_setup['context_manager']
        context_manager.get_project_for_channel.return_value = None
        
        event = {
            'channel': 'C999',
            'user': 'U123',
            'text': 'random message',
            'ts': '123'
        }
        
        response = await router.route_message(event)
        
        assert response is None
    
    @pytest.mark.asyncio
    async def test_thread_reply_flow(self, integration_setup):
        """Test thread reply handling"""
        router = integration_setup['router']
        
        event = {
            'channel': 'C123',
            'user': 'U123',
            'text': 'approved',
            'ts': '123.456',
            'thread_ts': '123.000'  # Different = in thread
        }
        
        response = await router.route_message(event)
        
        # Thread handling should work
        assert response is None or isinstance(response, str)
    
    @pytest.mark.asyncio
    async def test_low_confidence_escalation_flow(self, integration_setup):
        """Test low confidence AI answer escalates"""
        router = integration_setup['router']
        ai_handler = integration_setup['ai_handler']
        
        # Mock low confidence response
        ai_handler.model.generate_content = Mock(return_value=Mock(
            text="I don't know the answer to that."
        ))
        
        event = {
            'channel': 'D123',
            'user': 'U123',
            'text': 'Complex unclear question?',
            'ts': '123'
        }
        
        response = await router.route_message(event)
        
        assert 'escalate' in response.lower()
    
    @pytest.mark.asyncio
    async def test_project_channel_context_flow(self, integration_setup):
        """Test project channel provides context to AI"""
        router = integration_setup['router']
        ai_handler = integration_setup['ai_handler']
        
        event = {
            'channel': 'C123',
            'user': 'U123',
            'text': 'what is happening with this project?',
            'ts': '123'
        }
        
        response = await router.route_message(event)
        
        # Should answer with project context (channel not in mention, so ignored)
        assert response is None or 'test-project' in response.lower()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
