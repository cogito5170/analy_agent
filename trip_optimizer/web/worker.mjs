import Module from './engine.mjs';
import { callEngine } from './model.mjs';

let modPromise = null;

self.onmessage = async (e) => {
    const data = e.data;
    if (data.type === 'init') {
        if (!modPromise) {
            modPromise = Module();
        }
        await modPromise;
        self.postMessage({ type: 'ready' });
    } else if (data.type === 'optimize') {
        try {
            const mod = await modPromise;
            const plans = callEngine(mod, data.payload);
            self.postMessage({ type: 'success', numPlans: plans.length, plans });
        } catch (err) {
            self.postMessage({ type: 'error', error: err.message || String(err) });
        }
    }
};
