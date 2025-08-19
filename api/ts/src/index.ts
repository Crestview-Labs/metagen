// Metagen API Client v0.1.1
export * from '../generated/index.js';
export { MetagenStreamingClient, parseSSEStream, VERSION } from './streaming.js';
export type { StreamOptions, SSEMessage } from './streaming.js';
export { API_VERSION } from './version.js';

// Default export
import { MetagenStreamingClient } from './streaming.js';
export default MetagenStreamingClient;
