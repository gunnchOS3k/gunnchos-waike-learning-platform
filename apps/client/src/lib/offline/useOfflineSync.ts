import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { getOfflineStore } from "../tauriBridge";
import { SyncCoordinator, type CoordinatorState, type SyncTransport } from "./syncCoordinator";
import { deriveSyncUx, type SyncUxState } from "./syncUx";

/**
 * Real sync state for the banner. When there is no native store (browser dev/test
 * builds) the hook reports plain connectivity instead of inventing a queue — it
 * must never claim work is synced that it cannot see.
 */

export interface OfflineSyncView {
  ux: SyncUxState;
  state: CoordinatorState | null;
  coordinator: SyncCoordinator | null;
  refresh: () => Promise<void>;
  flush: () => Promise<void>;
}

export function useOfflineSync(args: {
  transport: SyncTransport | null;
  sectionId: string;
  deviceId: string;
  siteId: string | null;
  online: boolean;
}): OfflineSyncView {
  const { transport, sectionId, deviceId, siteId, online } = args;
  const [state, setState] = useState<CoordinatorState | null>(null);
  const store = useMemo(() => getOfflineStore(), []);
  const onlineRef = useRef(online);
  onlineRef.current = online;

  const coordinator = useMemo(() => {
    if (!store || !transport || !siteId) return null;
    return new SyncCoordinator({
      store,
      transport,
      deviceId,
      siteId,
      isOnline: () => onlineRef.current,
      onStateChange: setState,
    });
  }, [store, transport, deviceId, siteId]);

  const refresh = useCallback(async () => {
    if (!coordinator) return;
    setState(await coordinator.state(sectionId));
  }, [coordinator, sectionId]);

  const flush = useCallback(async () => {
    if (!coordinator) return;
    await coordinator.flush();
    await refresh();
  }, [coordinator, refresh]);

  // Adopt the durable queue on mount, then again whenever we regain connectivity.
  useEffect(() => {
    if (!coordinator) return;
    let alive = true;
    void coordinator
      .resume(sectionId)
      .then((s) => {
        if (alive) setState(s);
      })
      .catch(() => {
        /* a resume failure must not blank the banner */
      });
    return () => {
      alive = false;
    };
  }, [coordinator, sectionId]);

  useEffect(() => {
    if (!coordinator || !online) return;
    void flush();
  }, [coordinator, online, flush]);

  const ux: SyncUxState = state
    ? state.ux
    : deriveSyncUx({
        online,
        pendingCount: 0,
        syncing: false,
        lastStatus: null,
        ackPersisted: false,
      });

  return { ux, state, coordinator, refresh, flush };
}
