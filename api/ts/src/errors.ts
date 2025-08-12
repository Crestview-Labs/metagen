// Auto-generated error handling - DO NOT EDIT

export class APIError extends Error {
  constructor(
    public status: number,
    public statusText: string,
    public body?: any
  ) {
    super(`API Error ${status}: ${statusText}`);
    this.name = 'APIError';
  }
}

export class NetworkError extends Error {
  constructor(message: string, public cause?: Error) {
    super(message);
    this.name = 'NetworkError';
  }
}

export class StreamError extends Error {
  constructor(message: string, public cause?: Error) {
    super(message);
    this.name = 'StreamError';
  }
}

export class VersionMismatchError extends Error {
  constructor(expected: string, received: string) {
    super(`API version mismatch: expected ${expected}, received ${received}`);
    this.name = 'VersionMismatchError';
  }
}