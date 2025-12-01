"""Unit tests for llm_client.py CODER routing support."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, List

# Import the module under test
from brain.llm_client import chat, chat_async, _messages_to_prompt


class TestMessagesToPrompt:
    """Test the _messages_to_prompt helper function."""

    def test_single_user_message(self):
        """Test conversion of a single user message."""
        messages = [{"role": "user", "content": "Hello"}]
        result = _messages_to_prompt(messages)
        assert result == "User: Hello"

    def test_system_and_user_messages(self):
        """Test conversion with system and user messages."""
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "What is 2+2?"}
        ]
        result = _messages_to_prompt(messages)
        assert "System: You are a helpful assistant." in result
        assert "User: What is 2+2?" in result
        assert result.count("\n\n") == 1  # One separator between messages

    def test_conversation_with_assistant(self):
        """Test conversation with assistant response."""
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
            {"role": "user", "content": "How are you?"}
        ]
        result = _messages_to_prompt(messages)
        assert "User: Hello" in result
        assert "Assistant: Hi there!" in result
        assert "User: How are you?" in result


class TestChatAsync:
    """Test the async chat interface."""

    @pytest.mark.asyncio
    async def test_q4_routing(self):
        """Test that which='Q4' routes to kitty-q4 model."""
        messages = [{"role": "user", "content": "Test Q4"}]

        with patch('brain.llm_client._get_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.generate = AsyncMock(return_value={"response": "Q4 response"})
            mock_get_client.return_value = mock_client

            result = await chat_async(messages, which="Q4")

            # Verify generate was called with Q4 model
            mock_client.generate.assert_called_once()
            call_args = mock_client.generate.call_args
            assert call_args[1]["model"] == "kitty-q4"
            assert result == "Q4 response"

    @pytest.mark.asyncio
    async def test_deep_routing(self):
        """Test that which='DEEP' routes to kitty-f16 model (deep reasoner alias)."""
        messages = [{"role": "user", "content": "Test DEEP"}]

        with patch('brain.llm_client._get_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.generate = AsyncMock(return_value={"response": "DEEP response"})
            mock_get_client.return_value = mock_client

            result = await chat_async(messages, which="DEEP")

            # Verify generate was called with DEEP model (kitty-f16 alias)
            mock_client.generate.assert_called_once()
            call_args = mock_client.generate.call_args
            assert call_args[1]["model"] == "kitty-f16"
            assert result == "DEEP response"

    @pytest.mark.asyncio
    async def test_coder_routing(self):
        """Test that which='CODER' routes to kitty-coder model."""
        messages = [{"role": "user", "content": "Write a function to check if a number is prime"}]

        with patch('brain.llm_client._get_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.generate = AsyncMock(return_value={"response": "def is_prime(n): ..."})
            mock_get_client.return_value = mock_client

            result = await chat_async(messages, which="CODER")

            # Verify generate was called with CODER model
            mock_client.generate.assert_called_once()
            call_args = mock_client.generate.call_args
            assert call_args[1]["model"] == "kitty-coder"
            assert result == "def is_prime(n): ..."

    @pytest.mark.asyncio
    async def test_default_routing(self):
        """Test that default routing goes to Q4."""
        messages = [{"role": "user", "content": "Test default"}]

        with patch('brain.llm_client._get_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.generate = AsyncMock(return_value={"response": "Default response"})
            mock_get_client.return_value = mock_client

            # Call without specifying which (should default to Q4)
            result = await chat_async(messages)

            # Verify generate was called with Q4 model (default)
            mock_client.generate.assert_called_once()
            call_args = mock_client.generate.call_args
            assert call_args[1]["model"] == "kitty-q4"

    @pytest.mark.asyncio
    async def test_tools_passed_through(self):
        """Test that tools parameter is passed to generate()."""
        messages = [{"role": "user", "content": "Test with tools"}]
        tools = [{"type": "function", "function": {"name": "test_tool"}}]

        with patch('brain.llm_client._get_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.generate = AsyncMock(return_value={"response": "Response with tools"})
            mock_get_client.return_value = mock_client

            result = await chat_async(messages, which="Q4", tools=tools)

            # Verify tools were passed to generate
            mock_client.generate.assert_called_once()
            call_args = mock_client.generate.call_args
            assert call_args[1]["tools"] == tools

    @pytest.mark.asyncio
    async def test_tool_calls_logged(self):
        """Test that tool calls are logged when present."""
        messages = [{"role": "user", "content": "Test tool calls"}]

        with patch('brain.llm_client._get_client') as mock_get_client:
            mock_client = AsyncMock()
            # Simulate tool calls in response
            tool_call = MagicMock()
            tool_call.name = "test_function"
            mock_client.generate = AsyncMock(return_value={
                "response": "Response",
                "tool_calls": [tool_call]
            })
            mock_get_client.return_value = mock_client

            with patch('brain.llm_client.logger') as mock_logger:
                result = await chat_async(messages, which="Q4")

                # Verify tool calls were logged
                mock_logger.info.assert_called_once()
                log_message = mock_logger.info.call_args[0][0]
                assert "test_function" in log_message


class TestChatSync:
    """Test the synchronous chat interface."""

    def test_q4_routing_sync(self):
        """Test that sync chat routes Q4 correctly."""
        messages = [{"role": "user", "content": "Test Q4 sync"}]

        with patch('brain.llm_client._get_client') as mock_get_client:
            mock_client = MagicMock()

            # Mock asyncio.run to return synchronously
            with patch('brain.llm_client.asyncio.run') as mock_run:
                mock_run.return_value = {"response": "Q4 sync response"}

                mock_get_client.return_value = mock_client

                result = chat(messages, which="Q4")

                # Verify asyncio.run was called
                assert mock_run.called
                assert result == "Q4 sync response"

    def test_coder_routing_sync(self):
        """Test that sync chat routes CODER correctly."""
        messages = [{"role": "user", "content": "Write code"}]

        with patch('brain.llm_client._get_client') as mock_get_client:
            mock_client = MagicMock()

            # Mock asyncio.run to return synchronously
            with patch('brain.llm_client.asyncio.run') as mock_run:
                mock_run.return_value = {"response": "def foo(): pass"}

                mock_get_client.return_value = mock_client

                result = chat(messages, which="CODER")

                # Verify asyncio.run was called
                assert mock_run.called
                assert result == "def foo(): pass"


class TestCoderIntegration:
    """Integration-style tests for CODER functionality."""

    @pytest.mark.asyncio
    async def test_coder_code_generation_message(self):
        """Test CODER with code generation message."""
        messages = [
            {"role": "system", "content": "You are an expert Python programmer."},
            {"role": "user", "content": "Write a function to calculate factorial"}
        ]

        with patch('brain.llm_client._get_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.generate = AsyncMock(return_value={
                "response": "def factorial(n):\n    if n <= 1:\n        return 1\n    return n * factorial(n-1)"
            })
            mock_get_client.return_value = mock_client

            result = await chat_async(messages, which="CODER")

            # Verify the response contains code
            assert "def factorial" in result
            assert "return" in result

    @pytest.mark.asyncio
    async def test_coder_vs_q4_different_models(self):
        """Test that CODER and Q4 use different model aliases."""
        messages = [{"role": "user", "content": "Test"}]

        with patch('brain.llm_client._get_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.generate = AsyncMock(return_value={"response": "Response"})
            mock_get_client.return_value = mock_client

            # Call with Q4
            await chat_async(messages, which="Q4")
            q4_call_args = mock_client.generate.call_args

            # Reset mock
            mock_client.reset_mock()

            # Call with CODER
            await chat_async(messages, which="CODER")
            coder_call_args = mock_client.generate.call_args

            # Verify different models were used
            assert q4_call_args[1]["model"] == "kitty-q4"
            assert coder_call_args[1]["model"] == "kitty-coder"
            assert q4_call_args[1]["model"] != coder_call_args[1]["model"]


class TestErrorHandling:
    """Test error handling in llm_client."""

    @pytest.mark.asyncio
    async def test_client_initialization_error(self):
        """Test handling of client initialization errors."""
        messages = [{"role": "user", "content": "Test"}]

        with patch('brain.llm_client._get_client') as mock_get_client:
            mock_get_client.side_effect = Exception("Client initialization failed")

            with pytest.raises(Exception) as exc_info:
                await chat_async(messages, which="Q4")

            assert "Client initialization failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_generate_error(self):
        """Test handling of generate() errors."""
        messages = [{"role": "user", "content": "Test"}]

        with patch('brain.llm_client._get_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.generate = AsyncMock(side_effect=Exception("Generation failed"))
            mock_get_client.return_value = mock_client

            with pytest.raises(Exception) as exc_info:
                await chat_async(messages, which="CODER")

            assert "Generation failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_empty_response(self):
        """Test handling of empty response from generate()."""
        messages = [{"role": "user", "content": "Test"}]

        with patch('brain.llm_client._get_client') as mock_get_client:
            mock_client = AsyncMock()
            # Return empty response
            mock_client.generate = AsyncMock(return_value={"response": ""})
            mock_get_client.return_value = mock_client

            result = await chat_async(messages, which="Q4")

            # Should return empty string, not crash
            assert result == ""


# Test summary
def test_module_exports():
    """Test that module exports the expected functions."""
    from brain import llm_client

    assert hasattr(llm_client, 'chat')
    assert hasattr(llm_client, 'chat_async')
    assert callable(llm_client.chat)
    assert callable(llm_client.chat_async)
