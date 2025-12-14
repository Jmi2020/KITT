import { useState, useEffect, useRef, useCallback } from 'react';

export function useTypingActivity(decayMs: number = 300) {
  const [typingLevel, setTypingLevel] = useState(0);
  const lastInteractionTime = useRef(0);
  const frameRef = useRef<number>();

  const trigger = useCallback(() => {
    lastInteractionTime.current = Date.now();
    setTypingLevel(1.0);
  }, []);

  useEffect(() => {
    const animate = () => {
      const now = Date.now();
      const timeSince = now - lastInteractionTime.current;
      
      if (timeSince < decayMs) {
        // Linear decay from 1.0 to 0.0
        const newLevel = Math.max(0, 1.0 - (timeSince / decayMs));
        setTypingLevel(newLevel);
        frameRef.current = requestAnimationFrame(animate);
      } else if (typingLevel > 0) {
        setTypingLevel(0);
      }
    };

    if (typingLevel > 0) {
      frameRef.current = requestAnimationFrame(animate);
    }

    return () => {
      if (frameRef.current) cancelAnimationFrame(frameRef.current);
    };
  }, [typingLevel, decayMs]);

  return { typingLevel, trigger };
}
