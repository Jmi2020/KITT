import { useEffect, useState } from 'react';
import { connect, MqttClient } from 'mqtt';

export interface DeviceState {
  deviceId: string;
  status: string;
  payload: Record<string, unknown>;
}

export interface ConversationContextState {
  conversationId: string;
  lastIntent?: string;
  device?: Record<string, unknown>;
  state?: Record<string, unknown>;
}

interface KittyContext {
  devices: Record<string, DeviceState>;
  conversations: Record<string, ConversationContextState>;
}

const useKittyContext = (mqttUrl: string = import.meta.env.VITE_MQTT_URL || 'ws://localhost:9001') => {
  const [client, setClient] = useState<MqttClient | null>(null);
  const [context, setContext] = useState<KittyContext>({ devices: {}, conversations: {} });

  useEffect(() => {
    const mqttClient = connect(mqttUrl, {
      reconnectPeriod: 2000,
    });

    setClient(mqttClient);

    mqttClient.on('connect', () => {
      mqttClient.subscribe('kitty/devices/+/state');
      mqttClient.subscribe('kitty/ctx/+');
    });

    mqttClient.on('message', (topic, payload) => {
      try {
        const data = JSON.parse(payload.toString());
        if (topic.startsWith('kitty/devices/')) {
          const [, , deviceId] = topic.split('/');
          setContext((prev) => ({
            ...prev,
            devices: {
              ...prev.devices,
              [deviceId]: {
                deviceId,
                status: typeof data.status === 'string' ? data.status : 'unknown',
                payload: data,
              },
            },
          }));
        }
        if (topic.startsWith('kitty/ctx/')) {
          const [, , conversationId] = topic.split('/');
          setContext((prev) => ({
            ...prev,
            conversations: {
              ...prev.conversations,
              [conversationId]: {
                conversationId,
                lastIntent: data.last_intent || data.lastIntent,
                device: data.device,
                state: data.session_state || data.state,
              },
            },
          }));
        }
      } catch (error) {
        console.warn('Failed to parse MQTT payload', error);
      }
    });

    return () => {
      mqttClient.end(true);
      setClient(null);
    };
  }, [mqttUrl]);

  return { client, context };
};

export default useKittyContext;
