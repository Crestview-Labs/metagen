/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CancelablePromise } from '../core/CancelablePromise.js';
import { OpenAPI } from '../core/OpenAPI.js';
import { request as __request } from '../core/request.js';
export class TelemetryService {
    /**
     * Get Recent Traces
     * Get recent trace IDs.
     * @returns string Successful Response
     * @throws ApiError
     */
    public static getRecentTracesApiTelemetryTracesGet({
        limit = 20,
    }: {
        limit?: number,
    }): CancelablePromise<Array<string>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/telemetry/traces',
            query: {
                'limit': limit,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Trace
     * Get all spans for a trace.
     * @returns any Successful Response
     * @throws ApiError
     */
    public static getTraceApiTelemetryTracesTraceIdGet({
        traceId,
    }: {
        traceId: string,
    }): CancelablePromise<Record<string, any>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/telemetry/traces/{trace_id}',
            path: {
                'trace_id': traceId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Analyze Trace
     * Analyze a trace for performance issues.
     * @returns any Successful Response
     * @throws ApiError
     */
    public static analyzeTraceApiTelemetryTracesTraceIdAnalysisGet({
        traceId,
    }: {
        traceId: string,
    }): CancelablePromise<Record<string, any>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/telemetry/traces/{trace_id}/analysis',
            path: {
                'trace_id': traceId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Current Trace
     * Get the current active trace (useful for debugging stuck requests).
     * @returns any Successful Response
     * @throws ApiError
     */
    public static getCurrentTraceApiTelemetryDebugCurrentGet(): CancelablePromise<Record<string, any>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/telemetry/debug/current',
        });
    }
    /**
     * Get Memory Traces
     * Get recent traces from in-memory storage.
     * @returns string Successful Response
     * @throws ApiError
     */
    public static getMemoryTracesApiTelemetryMemoryTracesGet({
        limit = 10,
    }: {
        limit?: number,
    }): CancelablePromise<Array<string>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/telemetry/memory/traces',
            query: {
                'limit': limit,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Memory Trace
     * Get trace from in-memory storage.
     * @returns any Successful Response
     * @throws ApiError
     */
    public static getMemoryTraceApiTelemetryMemoryTracesTraceIdGet({
        traceId,
    }: {
        traceId: string,
    }): CancelablePromise<Record<string, any>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/telemetry/memory/traces/{trace_id}',
            path: {
                'trace_id': traceId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Trace Insights
     * Get intelligent analysis and insights for a trace.
     * @returns any Successful Response
     * @throws ApiError
     */
    public static getTraceInsightsApiTelemetryTracesTraceIdInsightsGet({
        traceId,
    }: {
        traceId: string,
    }): CancelablePromise<Record<string, any>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/telemetry/traces/{trace_id}/insights',
            path: {
                'trace_id': traceId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Trace Report
     * Get a formatted markdown report for a trace.
     * @returns string Successful Response
     * @throws ApiError
     */
    public static getTraceReportApiTelemetryTracesTraceIdReportGet({
        traceId,
    }: {
        traceId: string,
    }): CancelablePromise<Record<string, string>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/telemetry/traces/{trace_id}/report',
            path: {
                'trace_id': traceId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Latest Trace Insights
     * Get insights for the most recent trace.
     * @returns any Successful Response
     * @throws ApiError
     */
    public static getLatestTraceInsightsApiTelemetryLatestInsightsGet(): CancelablePromise<Record<string, any>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/telemetry/latest/insights',
        });
    }
    /**
     * Get Latest Trace Report
     * Get a formatted report for the most recent trace.
     * @returns string Successful Response
     * @throws ApiError
     */
    public static getLatestTraceReportApiTelemetryLatestReportGet(): CancelablePromise<Record<string, string>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/telemetry/latest/report',
        });
    }
}
