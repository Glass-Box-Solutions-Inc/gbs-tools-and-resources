"""
Tests for Channel Context Manager
"""

import pytest
import json
import tempfile
from pathlib import Path
from hitl.channel_context_manager import ChannelContextManager, ChannelMapping


@pytest.fixture
def temp_config():
    """Create temporary config file"""
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
        config = {
            "channels": {
                "C123": {
                    "project_name": "test-project",
                    "owner": "alex",
                    "description": "Test project"
                }
            },
            "admin_users": ["U_ADMIN"]
        }
        json.dump(config, f)
        return f.name


@pytest.fixture
def context_manager(temp_config):
    """Create ChannelContextManager with temp config"""
    return ChannelContextManager(config_path=temp_config)


class TestChannelContextManager:
    """Test cases for ChannelContextManager"""
    
    def test_initialization(self, context_manager):
        """Test manager initializes correctly"""
        assert len(context_manager.mappings) == 1
        assert len(context_manager.admin_users) == 1
    
    def test_get_project_for_channel(self, context_manager):
        """Test getting project for channel"""
        project = context_manager.get_project_for_channel('C123')
        assert project == 'test-project'
    
    def test_get_project_for_unknown_channel(self, context_manager):
        """Test getting project for unknown channel"""
        project = context_manager.get_project_for_channel('C999')
        assert project is None
    
    def test_get_mapping(self, context_manager):
        """Test getting channel mapping"""
        mapping = context_manager.get_mapping('C123')
        assert mapping is not None
        assert mapping.project_name == 'test-project'
        assert mapping.owner == 'alex'
    
    def test_register_channel(self, context_manager):
        """Test registering new channel"""
        success = context_manager.register_channel(
            'C456',
            'new-project',
            'brian',
            'New project description'
        )
        assert success
        assert context_manager.get_project_for_channel('C456') == 'new-project'
    
    def test_unregister_channel(self, context_manager):
        """Test unregistering channel"""
        success = context_manager.unregister_channel('C123')
        assert success
        assert context_manager.get_project_for_channel('C123') is None
    
    def test_is_admin(self, context_manager):
        """Test admin check"""
        assert context_manager.is_admin('U_ADMIN')
        assert not context_manager.is_admin('U_REGULAR')
    
    def test_add_admin(self, context_manager):
        """Test adding admin"""
        success = context_manager.add_admin('U_NEW_ADMIN')
        assert success
        assert context_manager.is_admin('U_NEW_ADMIN')
    
    def test_remove_admin(self, context_manager):
        """Test removing admin"""
        success = context_manager.remove_admin('U_ADMIN')
        assert success
        assert not context_manager.is_admin('U_ADMIN')
    
    def test_list_channels(self, context_manager):
        """Test listing all channels"""
        channels = context_manager.list_channels()
        assert len(channels) == 1
        assert 'C123' in channels
    
    def test_get_channels_by_project(self, context_manager):
        """Test getting channels by project"""
        channels = context_manager.get_channels_by_project('test-project')
        assert len(channels) == 1
        assert 'C123' in channels


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
