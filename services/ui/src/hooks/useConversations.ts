import { useCallback, useState } from 'react';
import { Message, ToolCall } from '../components/VoiceAssistant/ConversationMessage';

interface Conversation {
  id: string;
  title: string;
  messages: Message[];
  createdAt: Date;
  updatedAt: Date;
}

interface UseConversationsReturn {
  /** Current conversation */
  conversation: Conversation | null;
  /** All messages in current conversation */
  messages: Message[];
  /** Create a new conversation */
  createConversation: (title?: string) => Conversation;
  /** Add a user message */
  addUserMessage: (content: string) => Message;
  /** Add an assistant message (can be streaming) */
  addAssistantMessage: (content: string, tier?: string) => Message;
  /** Update a message (for streaming) */
  updateMessage: (id: string, updates: Partial<Message>) => void;
  /** Append content to a message (for streaming) */
  appendToMessage: (id: string, content: string) => void;
  /** Add a tool call to a message */
  addToolCall: (messageId: string, toolCall: ToolCall) => void;
  /** Update a tool call status */
  updateToolCall: (messageId: string, toolId: string, updates: Partial<ToolCall>) => void;
  /** Clear all messages */
  clearMessages: () => void;
  /** Load messages (for switching conversations) */
  loadMessages: (messages: Message[]) => void;
  /** Get conversation by ID */
  getConversation: (id: string) => Conversation | undefined;
}

/**
 * Hook for managing conversation state.
 * Tracks messages, tool calls, and conversation history.
 */
export function useConversations(): UseConversationsReturn {
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);

  const createConversation = useCallback((title?: string) => {
    const newConversation: Conversation = {
      id: `conv-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`,
      title: title || `Conversation ${new Date().toLocaleDateString()}`,
      messages: [],
      createdAt: new Date(),
      updatedAt: new Date(),
    };

    setConversation(newConversation);
    setMessages([]);

    return newConversation;
  }, []);

  const addUserMessage = useCallback((content: string) => {
    const message: Message = {
      id: `msg-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`,
      role: 'user',
      content,
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, message]);
    setConversation((prev) =>
      prev ? { ...prev, updatedAt: new Date() } : prev
    );

    return message;
  }, []);

  const addAssistantMessage = useCallback((content: string, tier?: string) => {
    const message: Message = {
      id: `msg-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`,
      role: 'assistant',
      content,
      timestamp: new Date(),
      tier,
      isStreaming: true,
    };

    setMessages((prev) => [...prev, message]);
    setConversation((prev) =>
      prev ? { ...prev, updatedAt: new Date() } : prev
    );

    return message;
  }, []);

  const updateMessage = useCallback((id: string, updates: Partial<Message>) => {
    setMessages((prev) =>
      prev.map((msg) => (msg.id === id ? { ...msg, ...updates } : msg))
    );
  }, []);

  const appendToMessage = useCallback((id: string, content: string) => {
    setMessages((prev) =>
      prev.map((msg) =>
        msg.id === id ? { ...msg, content: msg.content + content } : msg
      )
    );
  }, []);

  const addToolCall = useCallback((messageId: string, toolCall: ToolCall) => {
    setMessages((prev) =>
      prev.map((msg) =>
        msg.id === messageId
          ? { ...msg, toolCalls: [...(msg.toolCalls || []), toolCall] }
          : msg
      )
    );
  }, []);

  const updateToolCall = useCallback(
    (messageId: string, toolId: string, updates: Partial<ToolCall>) => {
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === messageId
            ? {
                ...msg,
                toolCalls: msg.toolCalls?.map((tool) =>
                  tool.id === toolId ? { ...tool, ...updates } : tool
                ),
              }
            : msg
        )
      );
    },
    []
  );

  const clearMessages = useCallback(() => {
    setMessages([]);
    setConversation((prev) =>
      prev ? { ...prev, messages: [], updatedAt: new Date() } : prev
    );
  }, []);

  const loadMessages = useCallback((newMessages: Message[]) => {
    setMessages(newMessages);
    setConversation((prev) =>
      prev ? { ...prev, updatedAt: new Date() } : prev
    );
  }, []);

  const getConversation = useCallback(
    (id: string) => {
      return conversation?.id === id ? conversation : undefined;
    },
    [conversation]
  );

  return {
    conversation,
    messages,
    createConversation,
    addUserMessage,
    addAssistantMessage,
    updateMessage,
    appendToMessage,
    addToolCall,
    updateToolCall,
    clearMessages,
    loadMessages,
    getConversation,
  };
}
