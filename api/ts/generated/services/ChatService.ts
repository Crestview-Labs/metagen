/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { AgentMessage } from '../models/AgentMessage.js';
import type { ApprovalRequestMessage } from '../models/ApprovalRequestMessage.js';
import type { ApprovalResponse } from '../models/ApprovalResponse.js';
import type { ApprovalResponseMessage } from '../models/ApprovalResponseMessage.js';
import type { ChatRequest } from '../models/ChatRequest.js';
import type { ErrorMessage } from '../models/ErrorMessage.js';
import type { SystemMessage } from '../models/SystemMessage.js';
import type { ThinkingMessage } from '../models/ThinkingMessage.js';
import type { ToolCallMessage } from '../models/ToolCallMessage.js';
import type { ToolErrorMessage } from '../models/ToolErrorMessage.js';
import type { ToolResultMessage } from '../models/ToolResultMessage.js';
import type { ToolStartedMessage } from '../models/ToolStartedMessage.js';
import type { UsageMessage } from '../models/UsageMessage.js';
import type { UserMessage } from '../models/UserMessage.js';
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
     * @returns any Server-Sent Event stream of messages
     * @throws ApiError
     */
    public static chatStreamApiChatStreamPost({
        requestBody,
    }: {
        requestBody: ChatRequest,
    }): CancelablePromise<(UserMessage | AgentMessage | SystemMessage | ThinkingMessage | ToolCallMessage | ApprovalRequestMessage | ApprovalResponseMessage | ToolStartedMessage | ToolResultMessage | ToolErrorMessage | UsageMessage | ErrorMessage)> {
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
