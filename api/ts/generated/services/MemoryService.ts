/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CancelablePromise } from '../core/CancelablePromise.js';
import { OpenAPI } from '../core/OpenAPI.js';
import { request as __request } from '../core/request.js';
export class MemoryService {
    /**
     * Clear History
     * Clear all conversation history and telemetry data from the database.
     * @returns string Successful Response
     * @throws ApiError
     */
    public static clearHistoryApiMemoryClearPost(): CancelablePromise<Record<string, string>> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/memory/clear',
        });
    }
}
