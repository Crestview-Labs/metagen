/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ToolsResponse } from '../models/ToolsResponse.js';
import type { CancelablePromise } from '../core/CancelablePromise.js';
import { OpenAPI } from '../core/OpenAPI.js';
import { request as __request } from '../core/request.js';
export class ToolsService {
    /**
     * Get Tools
     * Get list of available tools.
     * @returns ToolsResponse Successful Response
     * @throws ApiError
     */
    public static getToolsApiToolsGet(): CancelablePromise<ToolsResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/tools',
        });
    }
    /**
     * Get Google Tools
     * Get list of Google-specific tools.
     * @returns any Successful Response
     * @throws ApiError
     */
    public static getGoogleToolsApiToolsGoogleGet(): CancelablePromise<Record<string, any>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/tools/google',
        });
    }
}
