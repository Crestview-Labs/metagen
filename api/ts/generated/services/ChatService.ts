/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ApprovalResponse } from '../models/ApprovalResponse.js';
import type { ApprovalResponseMessage } from '../models/ApprovalResponseMessage.js';
import type { ChatRequest } from '../models/ChatRequest.js';
import type { CancelablePromise } from '../core/CancelablePromise.js';
import { OpenAPI } from '../core/OpenAPI.js';
import { request as __request } from '../core/request.js';
export class ChatService {
    /**
     * Handle Approval Response
     * Handle tool approval response.
     * @returns ApprovalResponse Successful Response
     * @throws ApiError
     */
    public static handleApprovalResponseApiChatApprovalResponsePost({
        requestBody,
    }: {
        requestBody: ApprovalResponseMessage,
    }): CancelablePromise<ApprovalResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/chat/approval-response',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Chat Stream
     * Stream chat responses as they are generated.
     * @returns any Successful Response
     * @throws ApiError
     */
    public static chatStreamApiChatStreamPost({
        requestBody,
    }: {
        requestBody: ChatRequest,
    }): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/chat/stream',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
