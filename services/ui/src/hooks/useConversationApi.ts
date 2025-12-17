import { useCallback, useState } from 'react';
import { Message, ToolCall } from '../components/VoiceAssistant/ConversationMessage';
import { ConversationSummary } from '../components/VoiceAssistant/ConversationSelector';

const API_BASE = '/api';

interface ConversationListResponse {
  conversations: Array<{
    conversationId: string;
    title: string;
    messageCount: number;
    lastMessage?: string;
    createdAt: string;
    lastMessageAt: string;
  }>;
  total?: number;
}

interface ConversationMessagesResponse {
  messages: Array<{
    id: string;
    role: 'user' | 'assistant' | 'system';
    content: string;
    tier?: string;
    tool_calls?: Array<{
      id: string;
      name: string;
      args?: Record<string, unknown>;
      result?: string;
      status: string;
    }>;
    created_at: string;
  }>;
}

interface UseConversationApiReturn {
  /** List of conversations */
  conversations: ConversationSummary[];
  /** Loading state */
  isLoading: boolean;
  /** Error state */
  error: string | null;
  /** Fetch all conversations */
  fetchConversations: () => Promise<ConversationSummary[]>;
  /** Fetch messages for a conversation */
  fetchMessages: (conversationId: string) => Promise<Message[]>;
  /** Rename a conversation */
  renameConversation: (conversationId: string, title: string) => Promise<void>;
  /** Delete a conversation */
  deleteConversation: (conversationId: string) => Promise<void>;
  /** Clear error */
  clearError: () => void;
}

/**
 * Hook for conversation API operations.
 * Provides CRUD operations for conversations and messages.
 */
export function useConversationApi(): UseConversationApiReturn {
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const cacheKey = 'kitty_conversations_cache';

  const fetchConversations = useCallback(async (): Promise<ConversationSummary[]> => {
    setIsLoading(true);
    setError(null);

    try {
      const response = await fetch(`${API_BASE}/conversations`);
      if (!response.ok) {
        throw new Error(`Failed to fetch conversations: ${response.statusText}`);
      }

      const data: ConversationListResponse = await response.json();

      const summaries: ConversationSummary[] = data.conversations.map((conv) => ({
        id: conv.conversationId,
        title: conv.title || `Conversation ${conv.conversationId.slice(0, 8)}`,
        messageCount: conv.messageCount,
        lastMessage: conv.lastMessage,
        createdAt: new Date(conv.createdAt),
        updatedAt: new Date(conv.lastMessageAt),
      }));

      // Sort by updated time, newest first
      summaries.sort((a, b) => b.updatedAt.getTime() - a.updatedAt.getTime());

      setConversations(summaries);
      // Cache for offline/fallback
      localStorage.setItem(cacheKey, JSON.stringify(summaries));
      return summaries;
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch conversations';
      setError(message);
      // Try cached copy if available
      const cached = localStorage.getItem(cacheKey);
      if (cached) {
        try {
          const parsed: ConversationSummary[] = JSON.parse(cached).map((conv: any) => ({
            ...conv,
            createdAt: new Date(conv.createdAt),
            updatedAt: new Date(conv.updatedAt),
          }));
          setConversations(parsed);
          return parsed;
        } catch {
          // ignore cache parse errors
        }
      }
      return [];
    } finally {
      setIsLoading(false);
    }
  }, []);

  const fetchMessages = useCallback(async (conversationId: string): Promise<Message[]> => {
    setIsLoading(true);
    setError(null);

    try {
      const response = await fetch(`${API_BASE}/conversations/${conversationId}/messages`);
      if (!response.ok) {
        if (response.status === 404) {
          // Conversation doesn't exist yet, return empty
          return [];
        }
        throw new Error(`Failed to fetch messages: ${response.statusText}`);
      }

      const data: ConversationMessagesResponse = await response.json();

      const messages: Message[] = data.messages.map((msg) => ({
        id: msg.id,
        role: msg.role,
        content: msg.content,
        tier: msg.tier,
        timestamp: new Date(msg.created_at),
        toolCalls: msg.tool_calls?.map((tc) => ({
          id: tc.id,
          name: tc.name,
          args: tc.args,
          result: tc.result,
          status: tc.status as ToolCall['status'],
        })),
      }));

      return messages;
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch messages';
      setError(message);
      return [];
    } finally {
      setIsLoading(false);
    }
  }, []);

  const renameConversation = useCallback(async (conversationId: string, title: string): Promise<void> => {
    setError(null);

    try {
      const response = await fetch(`${API_BASE}/conversations/${conversationId}/title`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ title }),
      });

      if (!response.ok) {
        throw new Error(`Failed to rename conversation: ${response.statusText}`);
      }

      // Update local state
      setConversations((prev) =>
        prev.map((conv) =>
          conv.id === conversationId
            ? { ...conv, title, updatedAt: new Date() }
            : conv
        )
      );
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to rename conversation';
      setError(message);
      throw err;
    }
  }, []);

  const deleteConversation = useCallback(async (conversationId: string): Promise<void> => {
    setError(null);

    try {
      const response = await fetch(`${API_BASE}/conversations/${conversationId}`, {
        method: 'DELETE',
      });

      if (!response.ok && response.status !== 404) {
        throw new Error(`Failed to delete conversation: ${response.statusText}`);
      }

      // Update local state
      setConversations((prev) => prev.filter((conv) => conv.id !== conversationId));
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to delete conversation';
      setError(message);
      throw err;
    }
  }, []);

  const clearError = useCallback(() => {
    setError(null);
  }, []);

  return {
    conversations,
    isLoading,
    error,
    fetchConversations,
    fetchMessages,
    renameConversation,
    deleteConversation,
    clearError,
  };
}
