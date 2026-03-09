(function () {
    const config = window.APP_CONFIG || {};
    const hub = window.liveDataHub;

    if (!hub) return;

    if (!config.SUPABASE_URL || !config.SUPABASE_ANON_KEY) {
        hub.setRealtimeStatus('disabled');
        return;
    }

    if (!window.supabase || typeof window.supabase.createClient !== 'function') {
        hub.setRealtimeStatus('disabled');
        return;
    }

    try {
        hub.setRealtimeStatus('connecting');

        const client = window.supabase.createClient(config.SUPABASE_URL, config.SUPABASE_ANON_KEY, {
            auth: {
                persistSession: false,
                autoRefreshToken: false,
                detectSessionInUrl: false,
            },
        });

        const channel = client
            .channel('ytd-live-sync')
            .on('postgres_changes', { event: '*', schema: 'public', table: 'cameras' }, () => {
                hub.notifyRealtime('cameras');
            })
            .on('postgres_changes', { event: '*', schema: 'public', table: 'camera_provisioning' }, () => {
                hub.notifyRealtime('camera_provisioning');
            })
            .on('postgres_changes', { event: '*', schema: 'public', table: 'violations' }, () => {
                hub.notifyRealtime('violations');
            })
            .on('postgres_changes', { event: '*', schema: 'public', table: 'detection_zones' }, () => {
                hub.notifyRealtime('detection_zones');
            })
            .subscribe((status) => {
                if (status === 'SUBSCRIBED') {
                    hub.setRealtimeStatus('subscribed');
                    hub.requestSync({ reason: 'realtime-subscribed' });
                    return;
                }

                if (status === 'CHANNEL_ERROR' || status === 'TIMED_OUT') {
                    hub.setRealtimeStatus('error');
                    return;
                }

                if (status === 'CLOSED') {
                    hub.setRealtimeStatus('disabled');
                }
            });

        window.addEventListener('beforeunload', () => {
            client.removeChannel(channel);
        });
    } catch (error) {
        console.error('Supabase realtime:', error);
        hub.setRealtimeStatus('error');
    }
})();
