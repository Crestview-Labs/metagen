// Metagen API Client v2025.08.19.152833
export * from '../generated/index.js';
export { MetagenStreamingClient, parseSSEStream, VERSION } from './streaming.js';
export type { StreamOptions, SSEMessage } from './streaming.js';
export { API_VERSION } from './version.js';

// Default export
import { MetagenStreamingClient } from './streaming.js';
export default MetagenStreamingClient;
