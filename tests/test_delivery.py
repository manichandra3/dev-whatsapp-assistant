"""
Tests for the DeliveryService.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.delivery.service import DeliveryService


@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def mock_llm():
    llm = AsyncMock()
    llm.chat.return_value = MagicMock(content="mocked summary")
    return llm


@pytest.fixture
def delivery_service(mock_db, mock_llm):
    return DeliveryService(mock_db, mock_llm)


@pytest.mark.asyncio
async def test_deliver_schedule_task(delivery_service, mock_db):
    metadata = {"task": "do something", "time": "2026-04-25T10:30:00+00:00", "frequency": "once"}
    response = await delivery_service.deliver("schedule_task", "do something", metadata, "user1", "remind me to do something tomorrow")
    
    assert "Got it" in response
    assert "do something" in response
    args = mock_db.save_scheduled_task.call_args[0]
    assert args[0] == "user1"
    assert args[1] == "do something"
    assert args[2] == "Time: 2026-04-25T10:30:00+00:00, Frequency: once"
    assert args[4] == "once"


@pytest.mark.asyncio
async def test_deliver_schedule_task_incomplete(delivery_service, mock_db):
    metadata = {"task": "do something"}
    response = await delivery_service.deliver("schedule_task", "do something", metadata, "user1", "remind me")
    
    assert "What time would you like to be reminded?" in response
    mock_db.save_scheduled_task.assert_not_called()


@pytest.mark.asyncio
async def test_deliver_schedule_task_invalid_time(delivery_service, mock_db):
    metadata = {"task": "do something", "time": "tomorrow evening"}
    response = await delivery_service.deliver("schedule_task", "do something", metadata, "user1", "remind me tomorrow evening")

    assert "need an exact date/time" in response
    mock_db.save_scheduled_task.assert_not_called()


@pytest.mark.asyncio
async def test_deliver_log_expense(delivery_service, mock_db):
    metadata = {"amount": "50", "currency": "USD", "category": "food"}
    response = await delivery_service.deliver("log_expense", "food", metadata, "user1", "spent 50 on food")
    
    assert "50" in response
    assert "USD" in response
    mock_db.log_expense.assert_called_once_with("user1", "50", "USD", "food", "", "spent 50 on food")


@pytest.mark.asyncio
async def test_deliver_general_chat(delivery_service, mock_db, mock_llm):
    mock_db.get_recent_messages.return_value = []
    mock_llm.chat.return_value = MagicMock(content="Hello there")
    
    response = await delivery_service.deliver("general_chat", "greeting", {}, "user1", "hi")
    
    assert response == "Hello there"
    mock_llm.chat.assert_called_once()
    mock_db.get_recent_messages.assert_called_once_with("user1", limit=6)


@pytest.mark.asyncio
async def test_deliver_summarize_link_text_only(delivery_service, mock_llm):
    mock_llm.chat.return_value = MagicMock(content="Here is the summary.")
    metadata = {"text": "Long text to summarize"}
    response = await delivery_service.deliver("summarize_link", "topic", metadata, "user1", "")
    
    assert "Here is the summary." in response
    mock_llm.chat.assert_called_once()


@pytest.mark.asyncio
@patch('urllib.request.urlopen')
async def test_deliver_summarize_link_url_valid(mock_urlopen, delivery_service, mock_llm):
    mock_llm.chat.return_value = MagicMock(content="URL Summary.")
    
    mock_response = MagicMock()
    mock_response.headers = {'Content-Type': 'text/html; charset=utf-8'}
    mock_response.read.return_value = b"<html>some text</html>"
    mock_response.geturl.return_value = "https://example.com"
    mock_urlopen.return_value.__enter__.return_value = mock_response
    
    metadata = {"url": "https://example.com"}
    response = await delivery_service.deliver("summarize_link", "topic", metadata, "user1", "")
    
    assert "URL Summary." in response
    mock_llm.chat.assert_called_once()


@pytest.mark.asyncio
async def test_deliver_summarize_link_url_invalid_scheme(delivery_service):
    metadata = {"url": "ftp://example.com/file"}
    response = await delivery_service.deliver("summarize_link", "topic", metadata, "user1", "")
    
    assert "valid HTTP/HTTPS URLs" in response


@pytest.mark.asyncio
@patch('urllib.request.urlopen')
async def test_deliver_summarize_link_url_invalid_type(mock_urlopen, delivery_service):
    mock_response = MagicMock()
    mock_response.headers = {'Content-Type': 'application/pdf'}
    mock_response.read.return_value = b"PDF content"
    mock_response.geturl.return_value = "https://example.com/doc.pdf"
    mock_urlopen.return_value.__enter__.return_value = mock_response
    
    metadata = {"url": "https://example.com/doc.pdf"}
    response = await delivery_service.deliver("summarize_link", "topic", metadata, "user1", "")
    
    assert "non-text type" in response


@pytest.mark.asyncio
async def test_deliver_debug_code(delivery_service, mock_llm):
    mock_llm.chat.return_value = MagicMock(content="You have a typo.")
    metadata = {"error": "SyntaxError", "code": "print(x"}
    response = await delivery_service.deliver("debug_code", "topic", metadata, "user1", "")
    
    assert "Debugging Analysis" in response
    assert "You have a typo." in response
    mock_llm.chat.assert_called_once()


@pytest.mark.asyncio
async def test_deliver_unknown_intent(delivery_service):
    response = await delivery_service.deliver("make_coffee", "topic", {}, "user1", "")
    assert "I understood you wanted to 'make_coffee'" in response
    

@pytest.mark.asyncio
async def test_deliver_execute_code_success(delivery_service, mock_db):
    metadata = {"code": "print('hello world')", "language": "python"}
    response = await delivery_service.deliver("execute_code", "test", metadata, "user1", "")
    
    assert "Execution successful" in response
    assert "hello world" in response
    mock_db.log_code_run.assert_called_once()
    args = mock_db.log_code_run.call_args[0]
    assert args[0] == "user1"
    assert args[1] == "python"
    assert args[3] == 0  # exit status 0


@pytest.mark.asyncio
async def test_deliver_execute_code_blocked(delivery_service):
    metadata = {"code": "import os; os.system('echo hi')", "language": "python"}
    response = await delivery_service.deliver("execute_code", "test", metadata, "user1", "")
    
    assert "Execution blocked" in response
    assert "unsafe patterns" in response


@pytest.mark.asyncio
async def test_deliver_execute_code_wrong_lang(delivery_service):
    metadata = {"code": "console.log('hi')", "language": "javascript"}
    response = await delivery_service.deliver("execute_code", "test", metadata, "user1", "")
    
    assert "only support executing Python code" in response


@pytest.mark.asyncio
async def test_deliver_execute_code_timeout(delivery_service, mock_db):
    metadata = {"code": "import time; time.sleep(10)", "language": "python"}
    response = await delivery_service.deliver("execute_code", "test", metadata, "user1", "")
    assert "timed out" in response.lower() or "timeout" in response.lower() or "failed" in response.lower() or "error" in response.lower()


@pytest.mark.asyncio
async def test_deliver_execute_code_memory_limit(delivery_service, mock_db):
    metadata = {"code": "x = 'x' * 100000000", "language": "python"}
    response = await delivery_service.deliver("execute_code", "test", metadata, "user1", "")
    assert response is not None


@pytest.mark.asyncio
async def test_deliver_general_chat_with_context(delivery_service, mock_db, mock_llm):
    mock_db.get_recent_messages.return_value = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there!"}
    ]
    mock_llm.chat.return_value = MagicMock(content="I remember you said Hello!")
    
    response = await delivery_service.deliver("general_chat", "greeting", {}, "user1", "hi again")
    
    assert response == "I remember you said Hello!"
    mock_llm.chat.assert_called_once()
    mock_db.get_recent_messages.assert_called_once_with("user1", limit=6)


@pytest.mark.asyncio
async def test_deliver_summarize_link_empty_content(delivery_service, mock_llm):
    metadata = {"text": ""}
    response = await delivery_service.deliver("summarize_link", "topic", metadata, "user1", "")
    
    assert "couldn't find any content" in response.lower()


@pytest.mark.asyncio
async def test_deliver_summarize_link_url_fetch_error(delivery_service):
    metadata = {"url": "https://this-domain-does-not-exist-12345.com"}
    response = await delivery_service.deliver("summarize_link", "topic", metadata, "user1", "")
    
    assert "couldn't fetch" in response.lower() or "error" in response.lower()


@pytest.mark.asyncio
async def test_deliver_schedule_task_minimal_time(delivery_service, mock_db):
    metadata = {"task": "test", "time": "2026-04-25 10:30"}
    response = await delivery_service.deliver("schedule_task", "test", metadata, "user1", "")
    
    assert "Got it" in response
    mock_db.save_scheduled_task.assert_called_once()


@pytest.mark.asyncio
async def test_deliver_schedule_task_with_frequency(delivery_service, mock_db):
    metadata = {"task": "daily standup", "time": "2026-04-25T09:00:00+00:00", "frequency": "daily"}
    response = await delivery_service.deliver("schedule_task", "daily standup", metadata, "user1", "")
    
    assert "Got it" in response
    assert "daily" in response.lower()
    args = mock_db.save_scheduled_task.call_args[0]
    assert args[4] == "daily"  # frequency
