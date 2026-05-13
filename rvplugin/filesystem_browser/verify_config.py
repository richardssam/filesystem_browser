import sys
import os
import json
from unittest.mock import MagicMock

# Mock xstudio modules
xstudio = MagicMock()
xstudio.core = MagicMock()
xstudio.plugin = MagicMock()

sys.modules["xstudio"] = xstudio
sys.modules["xstudio.core"] = xstudio.core
sys.modules["xstudio.plugin"] = xstudio.plugin

class MockConnection:
    pass

# Setup PluginBase mock
class MockPluginBase:
    def __init__(self, connection, name, qml_folder):
        self.attributes = {}
        
    def add_attribute(self, name, value, metadata, register_as_preference=False):
        class MockAttribute:
            def __init__(self, v):
                self.v = v
            def value(self):
                return self.v
            def set_value(self, v):
                self.v = v
            def expose_in_ui_attrs_group(self, group):
                pass
        
        attr = MockAttribute(value)
        self.attributes[name] = attr
        return attr
        
    def register_hotkey(self, *args):
        return "mock_uuid"
        
    def insert_menu_item(self, *args, **kwargs):
        pass
        
    def register_ui_panel_qml(self, *args):
        pass

xstudio.plugin.PluginBase = MockPluginBase

# Add plugin path
sys.path.append(os.path.dirname(__file__))

# Now import the plugin
from filesystem_browser import FilesystemBrowserPlugin

def test_config():
    plugin = FilesystemBrowserPlugin(MockConnection())
    
    print(f"Extensions: {len(plugin.extensions)}")
    print(f"Ignore Dirs: {len(plugin.ignore_dirs)}")
    print(f"Root Ignore Dirs: {len(plugin.root_ignore_dirs)}")
    print(f"Recursion Limit: {plugin.depth_limit_attr.value()}")
    
    # Check values from config.json
    assert ".mov" in plugin.extensions
    assert ".git" in plugin.ignore_dirs
    assert "/Applications" in plugin.root_ignore_dirs
    assert plugin.depth_limit_attr.value() == 6
    
    # Check start_search uses threshold
    # We can't easily check local var in start_search, but we can verify it runs without error
    plugin.start_search("/")
    
    print("Verification Passed!")

if __name__ == "__main__":
    test_config()
