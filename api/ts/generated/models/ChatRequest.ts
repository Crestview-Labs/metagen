/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ApprovalResponseMessage } from './ApprovalResponseMessage.js';
import type { UserMessage } from './UserMessage.js';
/**
 * Request to send a message to the agent.
 */
export type ChatRequest = {
    /**
     * Message to send to the agent - can be a string or a Message object
     */
    message: (string | UserMessage | ApprovalResponseMessage);
    /**
     * Session identifier for request routing
     */
    session_id: string;
};

