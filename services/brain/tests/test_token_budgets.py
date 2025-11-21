"""Tests for token budget management system (Option A)."""

import pytest
from brain.token_budgets import (
    TokenBudgetManager,
    BudgetAllocation,
    ModelBudget,
    summarize_conversation
)
from brain.agents.collective.judge_prompts import (
    build_judge_system_prompt,
    build_judge_user_prompt,
    deduplicate_kb_references,
    trim_proposals_to_budget
)


class TestTokenEstimation:
    """Test token counting and estimation."""

    def test_estimate_tokens_basic(self):
        """Test basic token estimation."""
        # ~4 chars per token, so 40 chars ≈ 10 tokens
        text = "This is a test of token estimation."  # 35 chars ≈ 8 tokens
        tokens = TokenBudgetManager.estimate_tokens(text)
        assert tokens == 8  # 35 // 4

    def test_estimate_tokens_empty(self):
        """Test empty string returns 0 tokens."""
        assert TokenBudgetManager.estimate_tokens("") == 0
        assert TokenBudgetManager.estimate_tokens(None) == 0

    def test_estimate_tokens_messages(self):
        """Test message list token estimation."""
        messages = [
            {"role": "user", "content": "Hello world"},  # 11 chars + 4 overhead = ~6 tokens
            {"role": "assistant", "content": "Hi there"},  # 8 chars + 4 overhead = ~6 tokens
        ]
        tokens = TokenBudgetManager.estimate_tokens_messages(messages)
        assert tokens > 0  # Should include content + overhead


class TestBudgetAllocation:
    """Test budget allocation tracking."""

    def test_budget_allocation_basic(self):
        """Test basic budget allocation."""
        alloc = BudgetAllocation("test", allocated_tokens=100, actual_tokens=50)
        assert alloc.remaining == 50
        assert alloc.utilization == 50.0
        assert not alloc.overflow

    def test_budget_allocation_overflow(self):
        """Test overflow detection."""
        alloc = BudgetAllocation("test", allocated_tokens=100, actual_tokens=150)
        assert alloc.remaining == 0
        assert alloc.utilization == 150.0
        alloc.overflow = True
        assert alloc.overflow


class TestAtheneBudget:
    """Test Athene specialist budget checking."""

    def test_athene_budget_within_limit(self):
        """Test Athene budget check within limits."""
        system_prompt = "You are a specialist."  # ~5 tokens
        conv_summary = "Recent conversation..."  # ~4 tokens
        kb_chunks = "KB context here..."  # ~4 tokens
        task_query = "What should we do?"  # ~5 tokens

        fits, allocations = TokenBudgetManager.check_athene_budget(
            system_prompt=system_prompt,
            conversation_summary=conv_summary,
            kb_chunks=kb_chunks,
            task_query=task_query,
            tools_json=None
        )

        assert fits  # Should fit within 24k budget
        assert len(allocations) == 4  # System, conv, kb, task

    def test_athene_budget_with_large_kb(self):
        """Test Athene budget with large KB context."""
        system_prompt = "You are a specialist." * 10
        conv_summary = "Recent conversation..." * 10
        kb_chunks = "KB context here..." * 3000  # ~12k tokens
        task_query = "What should we do?"

        fits, allocations = TokenBudgetManager.check_athene_budget(
            system_prompt=system_prompt,
            conversation_summary=conv_summary,
            kb_chunks=kb_chunks,
            task_query=task_query,
            tools_json=None
        )

        # Should still fit (12k KB + overhead < 24k)
        assert fits


class TestJudgeBudget:
    """Test Judge budget checking."""

    def test_judge_budget_within_limit(self):
        """Test Judge budget check within limits."""
        system_prompt = "You are the judge."
        conv_summary = "Recent conversation..."
        kb_chunks = "Full KB context..."
        proposals = ["Proposal 1", "Proposal 2", "Proposal 3"]
        task_query = "Decide on this task"

        fits, allocations = TokenBudgetManager.check_judge_budget(
            system_prompt=system_prompt,
            conversation_summary=conv_summary,
            kb_chunks=kb_chunks,
            proposals=proposals,
            task_query=task_query,
            tools_json=None
        )

        assert fits  # Should fit within 100k budget
        assert len(allocations) == 5  # System, conv, kb, proposals, task


class TestTextTrimming:
    """Test text trimming to budget."""

    def test_trim_to_budget_no_trim_needed(self):
        """Test trimming when text already fits."""
        text = "This is short."
        result = TokenBudgetManager.trim_to_budget(text, budget_tokens=100)
        assert text in result  # Original text preserved

    def test_trim_to_budget_preserve_beginning(self):
        """Test trimming preserves beginning by default."""
        text = "A" * 1000  # ~250 tokens
        result = TokenBudgetManager.trim_to_budget(text, budget_tokens=50, preserve_end=False)
        tokens = TokenBudgetManager.estimate_tokens(result)
        assert tokens <= 60  # Within budget (with marker overhead)
        assert "[trimmed end]" in result

    def test_trim_to_budget_preserve_end(self):
        """Test trimming preserves end when requested."""
        text = "A" * 1000  # ~250 tokens
        result = TokenBudgetManager.trim_to_budget(text, budget_tokens=50, preserve_end=True)
        tokens = TokenBudgetManager.estimate_tokens(result)
        assert tokens <= 60  # Within budget (with marker overhead)
        assert "[trimmed start]" in result


class TestConversationSummarization:
    """Test conversation summarization."""

    def test_summarize_empty_conversation(self):
        """Test summarizing empty conversation."""
        result = summarize_conversation([])
        assert result == ""

    def test_summarize_recent_messages(self):
        """Test summarization keeps recent messages."""
        messages = [
            {"role": "user", "content": "First message"},
            {"role": "assistant", "content": "First response"},
            {"role": "user", "content": "Second message"},
            {"role": "assistant", "content": "Second response"},
        ]

        result = summarize_conversation(messages, max_tokens=100)
        assert "Second message" in result  # Most recent kept
        assert "Second response" in result


class TestJudgePromptBuilder:
    """Test judge prompt builder functions."""

    def test_deduplicate_kb_references(self):
        """Test KB reference deduplication."""
        proposals = [
            "Based on [KB#123] and [KB#456]...",
            "According to [KB#123] and [KB#789]...",
            "Using [KB#456]...",
        ]

        refs = deduplicate_kb_references(proposals)
        assert refs == {"123", "456", "789"}

    def test_deduplicate_kb_references_no_refs(self):
        """Test deduplication with no KB refs."""
        proposals = ["No references here"]
        refs = deduplicate_kb_references(proposals)
        assert refs == set()

    def test_build_judge_system_prompt(self):
        """Test judge system prompt builder."""
        prompt = build_judge_system_prompt("council")
        assert "GPT-OSS 120B Judge" in prompt
        assert "council" in prompt.lower()

    def test_build_judge_user_prompt(self):
        """Test judge user prompt builder."""
        prompt = build_judge_user_prompt(
            task="Test task",
            conversation_summary="Recent chat...",
            kb_context="[KB#1] Context...",
            proposals=["Proposal 1", "Proposal 2"],
            plan_logs="Planning notes..."
        )

        assert "Test task" in prompt
        assert "Recent chat" in prompt
        assert "[KB#1]" in prompt
        assert "Proposal 1" in prompt
        assert "Proposal 2" in prompt
        assert "Planning notes" in prompt

    def test_trim_proposals_to_budget(self):
        """Test proposal trimming."""
        proposals = [
            "Proposal 1 " * 1000,  # ~2k tokens
            "Proposal 2 " * 1000,  # ~2k tokens
            "Proposal 3 " * 1000,  # ~2k tokens
        ]

        trimmed = trim_proposals_to_budget(proposals, max_tokens=1000)
        assert len(trimmed) == 3  # All proposals kept but trimmed

        # Check total is within budget
        total_tokens = sum(
            TokenBudgetManager.estimate_tokens(p) for p in trimmed
        )
        assert total_tokens <= 1100  # Within budget (with marker overhead)


class TestModelBudget:
    """Test ModelBudget configuration."""

    def test_athene_budget_valid(self):
        """Test Athene budget is valid."""
        budget = TokenBudgetManager.ATHENE_BUDGET
        assert budget.total_context == 32768
        assert budget.prompt_budget + budget.output_budget <= budget.total_context

    def test_judge_budget_valid(self):
        """Test Judge budget is valid."""
        budget = TokenBudgetManager.JUDGE_BUDGET
        assert budget.total_context == 131072
        assert budget.prompt_budget + budget.output_budget <= budget.total_context

    def test_budget_overflow_detection(self):
        """Test budget overflow is detected."""
        with pytest.raises(ValueError):
            ModelBudget(
                model_name="test",
                total_context=1000,
                prompt_budget=800,
                output_budget=300,  # 800 + 300 = 1100 > 1000
                allocations={}
            )
