/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { SystemInfo } from '../models/SystemInfo.js';
import type { CancelablePromise } from '../core/CancelablePromise.js';
import { OpenAPI } from '../core/OpenAPI.js';
import { request as __request } from '../core/request.js';
export class SystemService {
    /**
     * Get System Info
     * Get system information.
     * @returns SystemInfo Successful Response
     * @throws ApiError
     */
    public static getSystemInfoApiSystemInfoGet(): CancelablePromise<SystemInfo> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/system/info',
        });
    }
    /**
     * Health Check
     * Detailed health check.
     * @returns any Successful Response
     * @throws ApiError
     */
    public static healthCheckApiSystemHealthGet(): CancelablePromise<Record<string, any>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/system/health',
        });
    }
}
