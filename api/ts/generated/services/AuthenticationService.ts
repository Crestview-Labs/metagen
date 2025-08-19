/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { AuthLoginRequest } from '../models/AuthLoginRequest.js';
import type { AuthResponse } from '../models/AuthResponse.js';
import type { AuthStatus } from '../models/AuthStatus.js';
import type { CancelablePromise } from '../core/CancelablePromise.js';
import { OpenAPI } from '../core/OpenAPI.js';
import { request as __request } from '../core/request.js';
export class AuthenticationService {
    /**
     * Get Auth Status
     * Get current authentication status.
     * @returns AuthStatus Successful Response
     * @throws ApiError
     */
    public static getAuthStatusApiAuthStatusGet(): CancelablePromise<AuthStatus> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/auth/status',
        });
    }
    /**
     * Login
     * Initiate Google OAuth login flow.
     * @returns AuthResponse Successful Response
     * @throws ApiError
     */
    public static loginApiAuthLoginPost({
        requestBody,
    }: {
        requestBody?: AuthLoginRequest,
    }): CancelablePromise<AuthResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/auth/login',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Logout
     * Logout and revoke authentication.
     * @returns AuthResponse Successful Response
     * @throws ApiError
     */
    public static logoutApiAuthLogoutPost(): CancelablePromise<AuthResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/auth/logout',
        });
    }
}
