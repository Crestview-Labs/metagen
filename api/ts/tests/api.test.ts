// Basic API client tests
import { describe, it, expect } from 'vitest';
import { MetagenStreamingClient } from '../src/streaming.js';
import { API_VERSION } from '../src/version.js';

describe('MetagenStreamingClient', () => {
  it('should create an instance with default URL', () => {
    const client = new MetagenStreamingClient();
    expect(client).toBeDefined();
  });

  it('should create an instance with custom URL', () => {
    const client = new MetagenStreamingClient('http://localhost:3000');
    expect(client).toBeDefined();
  });

  it('should export version', () => {
    expect(API_VERSION).toBeDefined();
    expect(typeof API_VERSION).toBe('string');
  });
});