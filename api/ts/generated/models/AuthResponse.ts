/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { AuthStatus } from './AuthStatus.js';
/**
 * Authentication operation response.
 */
export type AuthResponse = {
    success: boolean;
    message?: (string | null);
    auth_url?: (string | null);
    status?: (AuthStatus | null);
};

