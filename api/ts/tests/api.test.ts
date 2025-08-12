// Basic API client tests
import { describe, it, expect } from 'vitest';
import { MetagenAPI } from '../src/api';
import { API_VERSION, BUILD_VERSION } from '../src/version';

describe('MetagenAPI', () => {
  it('should create an instance with default URL', () => {
    const api = new MetagenAPI();
    expect(api).toBeDefined();
  });

  it('should create an instance with custom URL', () => {
    const api = new MetagenAPI('http://localhost:3000');
    expect(api).toBeDefined();
  });

  it('should export correct version', () => {
    expect(API_VERSION).toBe('0.1.0');
    expect(BUILD_VERSION).toBe('2025.01.08.001');
  });
});