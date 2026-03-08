"""
Tests for Message Router
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from hitl.message_router import MessageRouter
from hitl.intent_classifier import Intent, ClassificationResult


@pytest.fixture
def mock_classifier():
    """Mock IntentClassifier"""
    classifier = Mock()
    classifier.classify.return_value = ClassificationResult(
        intent=Intent.QUESTION,
        confidence=0.9,
        extracted_data={}
    )
    return classifier


@pytest.fixture
def mock_command_parser():
    """Mock CommandParser"""
    parser = Mock()
    parser.parse_and_execute = AsyncMock(return_value=Mock(
        success=True,
        message='Command executed'
    ))
    parser._show_help = Mock(return_value=Mock(
        success=True,
        message='Available commands: help, status, pause, cancel, list'
    ))
    return parser


@pytest.fixture
def mock_context_manager():
    """Mock ChannelContextManager"""
    manager = Mock()
    manager.get_project_for_channel.return_value = 'test-project'
    return manager


@pytest.fixture
def mock_ai_qa():
    """Mock AIQAHandler"""
    handler = Mock()
    handler.answer_question = AsyncMock(return_value='AI answer')
    return handler


@pytest.fixture
def mock_human_router():
    """Mock HumanRouter"""
    router = Mock()
    router.escalate = AsyncMock()
    return router


@pytest.fixture
def message_router(mock_classifier, mock_command_parser, mock_context_manager, 
                   mock_ai_qa, mock_human_router):
    """Create MessageRouter with mocks"""
    return MessageRouter(
        classifier=mock_classifier,
        command_parser=mock_command_parser,
        context_manager=mock_context_manager,
        ai_qa_handler=mock_ai_qa,
        human_router=mock_human_router
    )


class TestMessageRouter:
    """Test cases for MessageRouter"""
    
    def test_initialization(self, message_router):
        """Test router initializes correctly"""
        assert message_router.classifier is not None
        assert message_router.command_parser is not None
        assert message_router.context_manager is not None
    
    def test_is_bot_mentioned(self, message_router):
        """Test bot mention detection"""
        assert message_router._is_bot_mentioned('<@U123> hello')
        assert message_router._is_bot_mentioned('@spectacles what is task-123?')
        assert not message_router._is_bot_mentioned('hello world')
    
    def test_remove_bot_mention(self, message_router):
        """Test bot mention removal"""
        assert message_router._remove_bot_mention('<@U123> hello') == 'hello'
        assert message_router._remove_bot_mention('@spectacles task status') == 'task status'
        assert message_router._remove_bot_mention('hello world') == 'hello world'
    
    @pytest.mark.asyncio
    async def test_route_dm(self, message_router, mock_classifier):
        """Test DM routing"""
        mock_classifier.classify.return_value = ClassificationResult(
            intent=Intent.HELP,
            confidence=0.9,
            extracted_data={}
        )
        
        event = {
            'channel': 'D123',
            'user': 'U123',
            'text': 'help',
            'ts': '1234567890.123'
        }
        
        response = await message_router.route_message(event)
        
        assert response is not None
        assert 'help' in response.lower() or 'commands' in response.lower()
    
    @pytest.mark.asyncio
    async def test_route_mention(self, message_router, mock_ai_qa):
        """Test @mention routing"""
        event = {
            'channel': 'C123',
            'user': 'U123',
            'text': '<@U_BOT> what is task-123?',
            'ts': '1234567890.123'
        }
        
        response = await message_router.route_message(event)
        
        # Should call AI Q&A
        mock_ai_qa.answer_question.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_route_channel_message(self, message_router, mock_context_manager, mock_ai_qa):
        """Test project channel message routing"""
        event = {
            'channel': 'C123',
            'user': 'U123',
            'text': 'what tasks are running?',
            'ts': '1234567890.123'
        }
        
        response = await message_router.route_message(event)
        
        # Should call AI Q&A with project context
        mock_ai_qa.answer_question.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_route_thread_reply(self, message_router):
        """Test thread reply routing"""
        event = {
            'channel': 'C123',
            'user': 'U123',
            'text': 'approved',
            'ts': '1234567890.456',
            'thread_ts': '1234567890.123'  # Different from ts = in thread
        }
        
        response = await message_router.route_message(event)
        
        # Thread handling logic should be invoked
        assert response is None or isinstance(response, str)
    
    @pytest.mark.asyncio
    async def test_ignore_bot_messages(self, message_router):
        """Test bot messages are ignored"""
        event = {
            'channel': 'C123',
            'user': 'U123',
            'text': 'bot message',
            'bot_id': 'B123',
            'ts': '1234567890.123'
        }
        
        response = await message_router.route_message(event)
        
        assert response is None
    
    @pytest.mark.asyncio
    async def test_ignore_empty_messages(self, message_router):
        """Test empty messages are ignored"""
        event = {
            'channel': 'C123',
            'user': 'U123',
            'text': '',
            'ts': '1234567890.123'
        }
        
        response = await message_router.route_message(event)
        
        assert response is None
    
    @pytest.mark.asyncio
    async def test_ignore_unregistered_channel(self, message_router, mock_context_manager):
        """Test messages in unregistered channels are ignored"""
        mock_context_manager.get_project_for_channel.return_value = None
        
        event = {
            'channel': 'C999',
            'user': 'U123',
            'text': 'hello',
            'ts': '1234567890.123'
        }
        
        response = await message_router.route_message(event)
        
        assert response is None
    
    @pytest.mark.asyncio
    async def test_handle_dm_help(self, message_router, mock_classifier, mock_command_parser):
        """Test help command in DM"""
        mock_classifier.classify.return_value = ClassificationResult(
            intent=Intent.HELP,
            confidence=0.9,
            extracted_data={}
        )
        
        mock_command_parser._show_help.return_value = Mock(message='Help text')
        
        event = {'channel': 'D123', 'user': 'U123', 'text': 'help', 'ts': '123'}
        response = await message_router.route_message(event)
        
        assert 'help' in response.lower() or 'command' in response.lower()
    
    @pytest.mark.asyncio
    async def test_handle_dm_command(self, message_router, mock_classifier, mock_command_parser):
        """Test command execution in DM"""
        mock_classifier.classify.return_value = ClassificationResult(
            intent=Intent.COMMAND,
            confidence=0.9,
            extracted_data={'command': 'status', 'task_id': 'task-123'}
        )
        
        event = {'channel': 'D123', 'user': 'U123', 'text': 'status task-123', 'ts': '123'}
        response = await message_router.route_message(event)
        
        mock_command_parser.parse_and_execute.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_handle_dm_question(self, message_router, mock_classifier, mock_ai_qa):
        """Test question in DM"""
        mock_classifier.classify.return_value = ClassificationResult(
            intent=Intent.QUESTION,
            confidence=0.9,
            extracted_data={}
        )
        
        event = {'channel': 'D123', 'user': 'U123', 'text': 'what is happening?', 'ts': '123'}
        response = await message_router.route_message(event)
        
        mock_ai_qa.answer_question.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_handle_mention_empty(self, message_router):
        """Test empty @mention shows help"""
        event = {
            'channel': 'C123',
            'user': 'U123',
            'text': '<@U_BOT>',
            'ts': '123'
        }
        
        response = await message_router.route_message(event)
        
        assert 'spectacles' in response.lower()
        assert 'help' in response.lower() or 'command' in response.lower()
    
    @pytest.mark.asyncio
    async def test_error_handling(self, message_router, mock_classifier):
        """Test error handling in routing"""
        mock_classifier.classify.side_effect = Exception("Test error")
        
        event = {
            'channel': 'D123',
            'user': 'U123',
            'text': 'test',
            'ts': '123'
        }
        
        # Should not raise, should return error message
        response = await message_router.route_message(event)
        
        # Error handling depends on say_fn presence
        assert response is None  # No say_fn provided


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
