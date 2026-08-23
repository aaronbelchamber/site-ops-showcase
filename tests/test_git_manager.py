import pytest
from unittest.mock import MagicMock
from src.git.manager import GitManager
from src.execution.base import CommandResult

@pytest.fixture
def mock_executor():
    executor = MagicMock()
    executor.execute.return_value = CommandResult(exit_code=0, stdout="", stderr="", success=True)
    return executor

def test_git_manager_is_initialized_true(mock_executor):
    mock_executor.execute.return_value = CommandResult(exit_code=0, stdout="true\n", stderr="", success=True)
    site_config = {"site_name": "test-site", "wp_path": "/var/www/html"}
    mgr = GitManager(site_config, mock_executor)
    
    assert mgr.is_initialized() is True
    mock_executor.execute.assert_called_with('cd "/var/www/html" && git rev-parse --is-inside-work-tree', timeout=60)

def test_git_manager_is_initialized_false(mock_executor):
    mock_executor.execute.return_value = CommandResult(exit_code=128, stdout="", stderr="Not a git repo", success=False)
    site_config = {"site_name": "test-site", "wp_path": "/var/www/html"}
    mgr = GitManager(site_config, mock_executor)
    
    assert mgr.is_initialized() is False

def test_extract_versions_from_update():
    site_config = {"site_name": "test-site", "wp_path": "/var/www/html"}
    mgr = GitManager(site_config, MagicMock())
    
    versions_before = {
        "core_version": "6.4.2",
        "plugins": {"woocommerce": "8.0.0", "yoast": "21.0"},
        "themes": {"twentytwentyfour": "1.0"}
    }
    versions_after = {
        "core_version": "6.5.0",
        "plugins": {"woocommerce": "8.1.0", "yoast": "21.0"},
        "themes": {"twentytwentyfour": "1.1"}
    }
    
    msg = mgr.extract_versions_from_update({"type": "all"}, versions_before, versions_after)
    assert "Updated themes and plugins" in msg
    assert "- Core: WordPress 6.4.2 → 6.5.0" in msg
    assert "- Plugin: WooCommerce 8.0.0 → 8.1.0" in msg or "- Plugin: woocommerce 8.0.0 → 8.1.0" in msg
    assert "- Theme: Twenty Twenty-Four 1.0 → 1.1" in msg or "- Theme: twentytwentyfour 1.0 → 1.1" in msg

def test_init_repo_workflow(mock_executor):
    # Sequence of mock outputs:
    # 1. is_initialized check -> False
    # 2. git init -> success
    # 3. check .gitignore -> failure (needs creation)
    # 4. create .gitignore -> success
    # 5. git add . -> success
    # 6. git commit -> success
    # 7. setup remote (gh repo create) -> success
    # 8. get_repo_status:
    #    - is_initialized -> True
    #    - branch -> main
    #    - remote -> origin
    #    - last commit -> hash|msg|author|date
    #    - status -> empty
    
    def side_effect(cmd, timeout=60):
        if "rev-parse --is-inside-work-tree" in cmd:
            return CommandResult(0, "true\n", "", True)
        if "rev-parse --abbrev-ref HEAD" in cmd:
            return CommandResult(0, "main\n", "", True)
        if "remote get-url origin" in cmd:
            return CommandResult(0, "git@github.com:user/wp-test-site.git\n", "", True)
        if 'git log -1' in cmd:
            return CommandResult(0, "abcdef123456|Initial commit|Admin|2026-08-20T07:00:00Z\n", "", True)
        if "git status --porcelain" in cmd:
            return CommandResult(0, "", "", True)
        return CommandResult(0, "done", "", True)
        
    mock_executor.execute.side_effect = side_effect
    site_config = {"site_name": "test-site", "wp_path": "/var/www/html"}
    mgr = GitManager(site_config, mock_executor)
    
    res = mgr.init_repo(force=True)
    assert res["success"] is True
    assert res["status"]["initialized"] is True
    assert res["status"]["branch"] == "main"

def test_push_to_github_success(mock_executor):
    mock_executor.execute.side_effect = [
        CommandResult(0, "true\n", "", True), # is_initialized
        CommandResult(0, "Everything up-to-date\n", "", True) # git push
    ]
    site_config = {"site_name": "test-site", "wp_path": "/var/www/html"}
    mgr = GitManager(site_config, mock_executor)
    
    res = mgr.push_to_github()
    assert res["success"] is True
