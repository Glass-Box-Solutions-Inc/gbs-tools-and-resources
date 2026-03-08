"""
Tests for Command Parser
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from hitl.command_parser import CommandParser, CommandResult
from persistence.constants import AgentState


@pytest.fixture
def mock_orchestrator():
    """Mock orchestrator"""
    orch = Mock()
    orch.resume_task = AsyncMock()
    return orch


@pytest.fixture
def mock_task_store():
    """Mock TaskStore"""
    store = Mock()
    store.db_path = '/tmp/test.db'
    store.get_task.return_value = {
        'task_id': 'task-123',
        'goal': 'Test goal',
        'current_state': 'RUNNING',
        'created_at': '2026-01-18',
        'updated_at': '2026-01-18'
    }
    store.update_task_state = Mock()
    return store


@pytest.fixture
def mock_context_manager():
    """Mock ChannelContextManager"""
    manager = Mock()
    manager.is_admin.return_value = True
    manager.admin_users = ['U_ADMIN']
    return manager


@pytest.fixture
def command_parser(mock_orchestrator, mock_task_store, mock_context_manager):
    """Create CommandParser instance"""
    return CommandParser(
        orchestrator=mock_orchestrator,
        task_store=mock_task_store,
        context_manager=mock_context_manager
    )


class TestCommandParser:
    """Test cases for CommandParser"""
    
    @pytest.mark.asyncio
    async def test_help_command(self, command_parser):
        """Test help command"""
        result = await command_parser.parse_and_execute('help', 'U123')
        assert result.success
        assert 'command' in result.message.lower()
    
    @pytest.mark.asyncio
    async def test_status_command(self, command_parser, mock_task_store):
        """Test status command"""
        result = await command_parser.parse_and_execute('status task-123', 'U123')
        assert result.success
        assert 'task-123' in result.message
    
    @pytest.mark.asyncio
    async def test_status_no_task_id(self, command_parser):
        """Test status command without task ID"""
        result = await command_parser.parse_and_execute('status', 'U123')
        assert not result.success
        assert 'specify a task' in result.message.lower()
    
    @pytest.mark.asyncio
    async def test_pause_command(self, command_parser, mock_task_store):
        """Test pause command"""
        result = await command_parser.parse_and_execute('pause task-123', 'U123')
        assert result.success
        mock_task_store.update_task_state.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_cancel_command(self, command_parser, mock_task_store):
        """Test cancel command"""
        result = await command_parser.parse_and_execute('cancel task-123', 'U123')
        assert result.success
        mock_task_store.update_task_state.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_create_channel_admin(self, command_parser, mock_context_manager):
        """Test channel creation as admin"""
        result = await command_parser.parse_and_execute(
            'create channel for test-project', 
            'U_ADMIN'
        )
        # Will fail without slack_client, but should not get permission error
        assert 'only admins' not in result.message.lower()
    
    @pytest.mark.asyncio
    async def test_create_channel_non_admin(self, command_parser, mock_context_manager):
        """Test channel creation as non-admin"""
        mock_context_manager.is_admin.return_value = False
        result = await command_parser.parse_and_execute(
            'create channel for test-project',
            'U_REGULAR'
        )
        assert not result.success
        assert 'only admins' in result.message.lower()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
