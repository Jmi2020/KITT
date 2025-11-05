import { useEffect, useState } from 'react';
import { fetchRemoteStatus } from '../utils/tailscaleMode';

const useRemoteMode = () => {
  const [remote, setRemote] = useState<boolean>(false);

  useEffect(() => {
    let mounted = true;
    fetchRemoteStatus().then((status) => {
      if (mounted) {
        setRemote(status.remote);
      }
    });
    const interval = setInterval(() => {
      fetchRemoteStatus().then((status) => {
        if (mounted) {
          setRemote(status.remote);
        }
      });
    }, 30000);
    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, []);

  return remote;
};

export default useRemoteMode;
