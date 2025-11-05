export interface RemoteStatus {
  remote: boolean;
  reason?: string;
}

export const fetchRemoteStatus = async (): Promise<RemoteStatus> => {
  try {
    const response = await fetch('/api/remote/status');
    if (!response.ok) {
      throw new Error('Failed to determine remote status');
    }
    return await response.json();
  } catch (error) {
    console.warn('Remote status fallback to local', error);
    return { remote: false, reason: 'fallback' };
  }
};
