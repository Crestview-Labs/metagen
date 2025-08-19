/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CancelablePromise } from '../core/CancelablePromise.js';
import { OpenAPI } from '../core/OpenAPI.js';
import { request as __request } from '../core/request.js';
export class DefaultService {
    /**
     * Root
     * Root endpoint.
     * @returns string Successful Response
     * @throws ApiError
     */
    public static rootGet(): CancelablePromise<Record<string, string>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/',
        });
    }
    /**
     * Health
     * Health check endpoint with detailed status.
     * @returns any Successful Response
     * @throws ApiError
     */
    public static healthHealthGet(): CancelablePromise<Record<string, any>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/health',
        });
    }
}
