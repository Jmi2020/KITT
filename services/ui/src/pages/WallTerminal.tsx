import useKittyContext from '../hooks/useKittyContext';

interface WallTerminalProps {
  remoteMode: boolean;
}

const WallTerminal = ({ remoteMode }: WallTerminalProps) => {
  const { context } = useKittyContext();
  const activeConversation = Object.values(context.conversations)[0];

  return (
    <section className="wall-terminal">
      <header>
        <h2>Wall Terminal</h2>
        {remoteMode && <span className="badge">Remote Read-Only</span>}
      </header>
      {activeConversation ? (
        <div className="conversation">
          <h3>Conversation {activeConversation.conversationId}</h3>
          <p>Last intent: {activeConversation.lastIntent ?? 'n/a'}</p>
          <pre>{JSON.stringify(activeConversation.state, null, 2)}</pre>
        </div>
      ) : (
        <p>No active conversation.</p>
      )}
    </section>
  );
};

export default WallTerminal;
