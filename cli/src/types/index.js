/**
 * Core type definitions for Ambient CLI
 */
export class AmbientError extends Error {
    code;
    details;
    constructor(message, code, details) {
        super(message);
        this.code = code;
        this.details = details;
        this.name = 'AmbientError';
    }
}
export class BackendError extends AmbientError {
    constructor(message, details) {
        super(message, 'BACKEND_ERROR', details);
        this.name = 'BackendError';
    }
}
export class ProfileError extends AmbientError {
    constructor(message, details) {
        super(message, 'PROFILE_ERROR', details);
        this.name = 'ProfileError';
    }
}
export class ProcessError extends AmbientError {
    constructor(message, details) {
        super(message, 'PROCESS_ERROR', details);
        this.name = 'ProcessError';
    }
}
